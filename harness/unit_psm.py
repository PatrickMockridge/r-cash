#!/usr/bin/env python3
"""PSM: par issuance and redemption, fees, signed debt and the buffer bound.

Requires a listed V4T system. The PSM is funded with REV, an empty-buffer
redemption is refused, a par buy mints the stablecoin and increases the signed
debt, and a redemption of vault-issued stablecoin drives the signed debt
negative — the peg mechanism.

Usage:
    python3 harness/unit_psm.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import deploy as node  # noqa: E402
from feed_refresh import feed_uri, set_price  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_v3 import call, check, faucet_top_up, one  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"
SCENARIOS = ROOT / "harness" / "scenarios"
REV_PRICE = 5_000_000
V4T_PRICE = 66_666
RATE = REV_PRICE * 100_000_000 // V4T_PRICE
REV_IN = 1_000_000
MINT = 100_000_000
FEE_BPS = 10


def render(name: str, values: dict[str, str]) -> str:
    text = (SCENARIOS / f"{name}.rho").read_text()
    for key, value in values.items():
        text = text.replace(key, value)
    return minify(text)


def psm_info(psm: str, secret: str) -> dict:
    return one(call(psm, "PegStabilityModule",
                    'PegStabilityModule!("info", *r) | for (@x <- r) { deployId!(x) }'),
               secret)[1]


def supply(sc_uri: str, secret: str) -> int:
    return one(call(sc_uri, "Stablecoin",
                    'Stablecoin!("supply", *r) | for (@x <- r) { deployId!(x) }'),
               secret)[1]


def fee_ceil(amount: int) -> int:
    return (amount * FEE_BPS + 9999) // 10000


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    registry = state["oracle_registry_uri"]
    currency_registry = state["currency_registry_uri"]
    deployer = keys["deployer"]["secret"]

    set_price(keys, feed_uri(keys, root, registry, "REV", [REV_PRICE] * 3), "REV", REV_PRICE)
    set_price(keys, feed_uri(keys, root, registry, "V4T", [V4T_PRICE] * 3), "V4T", V4T_PRICE)

    entry = one(call(currency_registry, "CurrencyRegistry",
                     'CurrencyRegistry!("currency", "V4T", *r) | '
                     "for (@x <- r) { deployId!(x) }"), deployer)
    check("V4T listed", entry[0], True)
    entry = entry[1]
    vault, psm, stablecoin = entry["vaultUri"], entry["psmUri"], entry["stablecoinUri"]

    actor = keys["key14"]
    funder = keys["key15"]
    seller = keys["key16"]
    for key in (actor, funder, seller):
        faucet_top_up(key["address"])

    start = psm_info(psm, deployer)
    check("psm fee from params", start["feeBps"], FEE_BPS)

    # A tiny buffer cannot cover a redemption: refuse and return the payment.
    fund1 = render("stablecoin_psm_fund", {"__ROOT_URI__": root, "__PSM_URI__": psm,
                                           "__PSM_REV__": "1000000"})
    check("fund small buffer", one(fund1, actor["secret"])[0], (True, 1_000_000))
    small = psm_info(psm, deployer)
    check("small buffer balance", small["revBalance"], 1_000_000)

    sell_empty = render("stablecoin_psm_sell_only", {
        "__ROOT_URI__": root, "__VAULT_URI__": vault, "__PSM_URI__": psm,
        "__PUBKEY__": actor["public"], "__FUND__": "15000000",
        "__COLLATERAL__": "8000000", "__MINT__": str(MINT), "__MIN_REV__": "0",
    })
    refused = one(sell_empty, actor["secret"])
    check("empty buffer redemption refused", refused[0], False)
    check("empty buffer reason", refused[1], "buffer")

    fund2 = render("stablecoin_psm_fund", {"__ROOT_URI__": root, "__PSM_URI__": psm,
                                           "__PSM_REV__": "2000000"})
    one(fund2, funder["secret"])

    before_buy = psm_info(psm, deployer)
    supply_before = supply(stablecoin, deployer)
    buy = render("stablecoin_psm_buy", {
        "__ROOT_URI__": root, "__PSM_URI__": psm, "__PUBKEY__": funder["public"],
        "__REV_IN__": str(REV_IN), "__MIN_STABLE__": "0",
    })
    stable_out, fee = one(buy, funder["secret"])
    gross = REV_IN * RATE // 100_000_000
    check("buy gross", gross, RATE // 100)
    check("buy fee", fee, fee_ceil(gross))
    check("buy output", stable_out, gross - fee_ceil(gross))
    after_buy = psm_info(psm, deployer)
    check("psm debt after buy", after_buy["stableDebt"],
          before_buy["stableDebt"] + stable_out)
    check("psm rev after buy", after_buy["revBalance"],
          before_buy["revBalance"] + REV_IN)
    check("supply after buy", supply(stablecoin, deployer) - supply_before, stable_out)

    # Redeem vault-issued stablecoin: the debt goes negative, which is the par
    # floor working for stablecoin the PSM never minted.
    supply_before_sell = supply(stablecoin, deployer)
    debt_before_sell = after_buy["stableDebt"]
    sell = render("stablecoin_psm_sell_only", {
        "__ROOT_URI__": root, "__VAULT_URI__": vault, "__PSM_URI__": psm,
        "__PUBKEY__": seller["public"], "__FUND__": "15000000",
        "__COLLATERAL__": "8000000", "__MINT__": str(MINT), "__MIN_REV__": "0",
    })
    rev_out, fee_rev = one(sell, seller["secret"])
    gross_rev = MINT * 100_000_000 // RATE
    check("sell gross", gross_rev, fee_rev + rev_out)
    check("sell fee", fee_rev, fee_ceil(gross_rev))
    check("sell output", rev_out, gross_rev - fee_ceil(gross_rev))
    after_sell = psm_info(psm, deployer)
    check("psm debt after sell", after_sell["stableDebt"], debt_before_sell - MINT)
    check("psm debt is negative", after_sell["stableDebt"] < 0, True)
    # The sell scenario mints and burns the same amount, so the net supply delta is 0;
    # the burn is proven by the PSM debt and the S3 identity.
    check("supply delta after mint and burn",
          supply_before_sell - supply(stablecoin, deployer), 0)
    check("psm rev after sell", after_sell["revBalance"],
          after_buy["revBalance"] - rev_out)

    totals = one(call(vault, "VaultBook",
                      'VaultBook!("totals", *r) | for (@x <- r) { deployId!(x) }'),
                 deployer)[1]
    check("S3 with signed psm debt",
          totals["totalDebt"] + totals["sin"] + totals["psmDebt"],
          supply(stablecoin, deployer) + totals["totalAccruedInterest"])

    print(f"psm start {start}")
    print(f"psm after buy {after_buy}")
    print(f"psm after sell {after_sell} (negative debt is the par floor)")
    print("unit_psm: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
