#!/usr/bin/env python3
"""Exercise liquidation and bad-debt write-off on the v0.4 stablecoin issuer.

Deploys an isolated currency system (V5T), mints near the MCR against REV, then
moves the REV oracle down through a partial liquidation and a fully underwater
write-off. Checks the close factor, the bonus seizure, the bad-debt accounting
and the capability refusal on the direct VaultBook arm.

Usage:
    python3 harness/unit_liquidation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import sign_payload  # noqa: E402
from feed_refresh import feed_uri, set_price  # noqa: E402
from install_v3 import render  # noqa: E402
from unit_feed import blake2b256, canonical  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_stablecoin import deploy_system  # noqa: E402
from unit_v3 import call, check, one  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"
SCENARIOS = ROOT / "harness" / "scenarios"
PHLO = 100_000_000
CURRENCY = "V5T"
QUOTE_PRICE = 66_666
REV_HIGH = 5_000_000
REV_MID = 3_000_000
REV_LOW = 50_000
COLLATERAL = 10_000_000
MINT = 370_000_000


def render_scenario(name: str, values: dict) -> str:
    text = (SCENARIOS / name).read_text()
    for key, value in values.items():
        text = text.replace(key, value)
    return minify(text)


def vault_view(keys: dict, vault_uri: str, owner_id: str) -> dict:
    return one(call(vault_uri, "VaultBook",
                    f'VaultBook!("vault", "{owner_id}", *r) | '
                    "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])[1]


def totals(keys: dict, vault_uri: str) -> dict:
    return one(call(vault_uri, "VaultBook",
                    'VaultBook!("totals", *r) | '
                    "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])[1]


def supply(keys: dict, sc_uri: str) -> int:
    return one(call(sc_uri, "Stablecoin",
                    'Stablecoin!("supply", *r) | for (@x <- r) { deployId!(x) }'),
               keys["deployer"]["secret"])[1]


def check_invariant(label: str, keys: dict, sc_uri: str, vault_uri: str) -> dict:
    tot = totals(keys, vault_uri)
    check(f"{label}: debt + badDebt == supply + interest",
          tot["totalDebt"] + tot["badDebt"],
          supply(keys, sc_uri) + tot["totalAccruedInterest"])
    return tot


def liquidate(keys: dict, holder: str, liq_uri: str, vault_uri: str,
              owner_id: str, amount: int, min_collateral: int = 0) -> list:
    term = render_scenario("stablecoin_liquidate.rho", {
        "__HOLDER_URI__": holder,
        "__LIQ_URI__": liq_uri,
        "__VAULT_URI__": vault_uri,
        "__OWNER_ID__": owner_id,
        "__AMOUNT__": str(amount),
        "__MIN_COLLATERAL__": str(min_collateral),
    })
    return one(term, keys["deployer"]["secret"])


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    registry = state["oracle_registry_uri"]
    secret = keys["deployer"]["secret"]
    sponsor = keys["sponsor"]["public"]
    params = ('{"mcrBps": 20000, "bonusBps": 800, "closeFactorBps": 5000, '
              '"ratePerBlock": 3171, "debtCeiling": 10000000000000, '
              '"minDebt": 1000000, "maxDebt": 10000000000000, '
              '"maxOracleAge": 50}')
    values = [CURRENCY, "20000", "800", "5000", "3171", "10000000000000",
              "1000000", "10000000000000", "50"]
    params_hash = blake2b256(canonical("rcash:stablecoin-params:v1", values))
    payload = f"rcash:stablecoin-create:v1|{CURRENCY}|{params_hash}|{sponsor}"
    sig = sign_payload.sign_payload(keys["sponsor"]["secret"],
                                    payload.encode())["signature"]
    term = render("31_stablecoin", {
        "__ROOT_URI__": root,
        "__CURRENCY__": CURRENCY,
        "__PARAMS__": params,
        "__PARAMS_HASH__": params_hash,
        "__SPONSOR_PUB__": sponsor,
        "__SPONSOR_SIG__": sig,
    })
    system = deploy_system(term, secret)
    sc_uri, custody_uri, params_uri, vault_uri, liq_uri, att_reply = system
    check("liquidation engine attestation", att_reply[1].get("template") is not None, True)
    print(f"stablecoin: {sc_uri}")
    print(f"liquidation engine: {liq_uri}")

    rev_feed = feed_uri(keys, root, registry, "REV", [REV_HIGH, REV_HIGH, REV_HIGH])
    quote_feed = feed_uri(keys, root, registry, CURRENCY, [QUOTE_PRICE] * 3)
    set_price(keys, quote_feed, CURRENCY, QUOTE_PRICE)
    set_price(keys, rev_feed, "REV", REV_HIGH)

    owner_key = keys["key13"]["public"]
    mint_term = render_scenario("stablecoin_mint_hold.rho", {
        "__ROOT_URI__": root,
        "__SC_URI__": sc_uri,
        "__VAULT_URI__": vault_uri,
        "__PUBKEY__": owner_key,
        "__FUND__": "20000000",
        "__COLLATERAL__": str(COLLATERAL),
        "__MINT__": str(MINT),
    })
    holder, owner_id = one(mint_term, keys["key13"]["secret"])
    view = vault_view(keys, vault_uri, owner_id)
    check("minted debt", view["debt"] >= MINT, True)
    check("collateral", view["collateral"], COLLATERAL)
    check("healthy at mint", view["health"], True)

    # Partial liquidation: REV falls enough to break the MCR, but the vault still
    # covers the repay plus the 8% bonus.
    set_price(keys, quote_feed, CURRENCY, QUOTE_PRICE)
    set_price(keys, rev_feed, "REV", REV_MID)
    view = vault_view(keys, vault_uri, owner_id)
    check("unhealthy after drop", view["health"], False)

    repay1 = 185_000_000
    summary1, after1, totals1 = liquidate(keys, holder, liq_uri, vault_uri, owner_id, repay1)
    after1, totals1 = after1[1], totals1[1]
    check("partial: repaid", summary1["repaid"], repay1)
    check("partial: bad debt", summary1["badDebt"], 0)
    check("partial: seized", summary1["seized"] > 0 and summary1["seized"] < COLLATERAL, True)
    check("partial: collateral falls", after1["collateral"], COLLATERAL - summary1["seized"])
    check("partial: debt falls", after1["debt"] < MINT, True)
    check("partial: totals bad debt", totals1["badDebt"], 0)
    check_invariant("partial", keys, sc_uri, vault_uri)

    # Deep drop and write-off: the collateral cannot cover the close-factor slice,
    # so the vault is cleared at collateral value and the residual becomes bad debt.
    set_price(keys, quote_feed, CURRENCY, QUOTE_PRICE)
    set_price(keys, rev_feed, "REV", REV_LOW)
    view = vault_view(keys, vault_uri, owner_id)
    check("unhealthy after deep drop", view["health"], False)
    repay2 = (view["debt"] + 1) // 2

    summary2, after2, totals2 = liquidate(keys, holder, liq_uri, vault_uri, owner_id, repay2)
    after2, totals2 = after2[1], totals2[1]
    check("write-off: repaid", summary2["repaid"], repay2)
    check("write-off: bad debt", summary2["badDebt"] > 0, True)
    check("write-off: collateral seized", after2["collateral"], 0)
    check("write-off: debt cleared", after2["debt"], 0)
    check("write-off: bad debt booked", totals2["badDebt"] >= summary2["badDebt"], True)
    check_invariant("write-off", keys, sc_uri, vault_uri)

    # Direct VaultBook access without the liquidation cap must be refused.
    refusal = render_scenario("stablecoin_auth_refusal.rho", {
        "__HOLDER_URI__": holder,
        "__VAULT_URI__": vault_uri,
        "__OWNER_ID__": owner_id,
        "__AMOUNT__": "1",
    })
    check("liquidation authority refusal", one(refusal, secret), "refused")

    print(json.dumps({"stablecoin_uri": sc_uri, "liquidation_uri": liq_uri,
                      "vault_uri": vault_uri, "owner": owner_id,
                      "partial": summary1, "writeOff": summary2,
                      "totals": totals2}, indent=2))
    print("unit_liquidation: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
