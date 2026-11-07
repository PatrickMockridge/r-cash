#!/usr/bin/env python3
"""Savings yield: interest paid on a repay raises the savers' share value.

Requires a listed V4T system (run `make unit-stablecoin` first). The saver deposits
into the savings pool; a second owner mints in a later block and repays with
interest. The repay waterfall must deposit the interest into the surplus buffer,
cover outstanding sin, move the configured share to the savings pool, and leave
the rest in the buffer. The saver then withdraws more than the deposit.

In the multi-term split these URIs name T3 (`31_buffer_savings.rho`):
`savingsUri` is `SavingsPool` and `bufferUri` is `SurplusBuffer`. The privileged
buffer mutations run through the provisioned `BufferOperatorFacet`, so the suite
checks the term attestations and assumes `unit_stablecoin` completed the three
provisioning deploys (MULTI-TERM.md §4). `stablecoin_support.py` owns those
deploys; if it exposes `ensure_provisioned` this suite calls it.

Usage:
    python3 harness/unit_savings.py
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

import netconfig  # noqa: E402

import deploy as node  # noqa: E402
from feed_refresh import feed_uri, set_price  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_v3 import call, check, faucet_top_up, one  # noqa: E402

KEYS = netconfig.KEYS_PATH
STATE = netconfig.STATE_PATH
SCENARIOS = ROOT / "harness" / "scenarios"
MINT = 100_000_000
REPAY = 99_000_000


def render(name: str, values: dict[str, str]) -> str:
    text = (SCENARIOS / f"{name}.rho").read_text()
    for key, value in values.items():
        text = text.replace(key, value)
    return minify(text)


def savings_info(savings_uri: str, signer_secret: str) -> dict:
    return one(call(savings_uri, "SavingsPool",
                    'SavingsPool!("info", *r) | for (@x <- r) { deployId!(x) }'),
               signer_secret)[1]


def buffer_info(secret: str, buffer_uri: str) -> dict:
    return one(call(buffer_uri, "SurplusBuffer",
                    'SurplusBuffer!("info", *r) | for (@x <- r) { deployId!(x) }'),
               secret)[1]


def attest(uri: str, binding: str, secret: str) -> dict:
    return one(call(uri, binding,
                    f'{binding}!("attest", *r) | for (@x <- r) {{ deployId!(x) }}'),
               secret)[1]


def ensure_provisioned() -> None:
    """Ensure T3's BurnFacet and T2's operator facet were provisioned.

    `unit_stablecoin` performs the three provisioning deploys (T2 five kinds,
    T4 two, T3 one) through `stablecoin_support.py`. This suite runs after it;
    if the support helper exists, use it so a standalone run cannot hang on an
    unfilled bare-name slot. Missing helper: report, do not reimplement the
    sponsor-signed preimage here.
    """
    try:
        import stablecoin_support
    except ImportError:
        print("note: stablecoin_support.py missing; assuming unit_stablecoin "
              "provisioned the T3 BurnFacet")
        return
    ensure = getattr(stablecoin_support, "ensure_provisioned", None)
    if ensure is None:
        print("note: stablecoin_support.ensure_provisioned missing; assuming "
              "unit_stablecoin provisioned the T3 BurnFacet")
        return
    ensure(KEYS, "V4T")


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    registry = state["oracle_registry_uri"]
    currency_registry = state["currency_registry_uri"]
    deployer = keys["deployer"]["secret"]

    set_price(keys, feed_uri(keys, root, registry, "REV", [5_000_000] * 3), "REV", 5_000_000)
    set_price(keys, feed_uri(keys, root, registry, "V4T", [66_666] * 3), "V4T", 66_666)

    entry = one(call(currency_registry, "CurrencyRegistry",
                     'CurrencyRegistry!("currency", "V4T", *r) | '
                     "for (@x <- r) { deployId!(x) }"), deployer)
    check("V4T listed", entry[0], True)
    entry = entry[1]
    vault = entry["vaultUri"]
    savings = entry["savingsUri"]
    buffer = entry["bufferUri"]
    ensure_provisioned()
    savings_att = attest(savings, "SavingsPool", deployer)
    buffer_att = attest(buffer, "SurplusBuffer", deployer)
    check("savings term kind", savings_att.get("kind"), "savings")
    check("buffer term kind", buffer_att.get("kind"), "buffer")
    check("savings term currency", savings_att.get("currency"), "V4T")
    check("buffer term currency", buffer_att.get("currency"), "V4T")

    saver = keys["key13"]
    borrower = keys["key17"]
    for key in (saver, borrower):
        faucet_top_up(key["address"])

    hold = render("stablecoin_savings_hold", {
        "__ROOT_URI__": root,
        "__VAULT_URI__": vault, "__CURRENCY__": "V4T",
        "__SAVINGS_URI__": savings,
        "__PUBKEY__": saver["public"],
        "__FUND__": "15000000",
        "__COLLATERAL__": "8000000",
        "__MINT__": str(MINT),
        "__ASSET__": "V4T",
    })
    owner_id, shares = one(hold, saver["secret"])
    check("savings first deposit shares", shares, MINT)
    before = savings_info(savings, deployer)
    check("savings assets before", before["totalAssets"], MINT)
    check("savings share value before", before["shareValueE8"], 100_000_000)

    mint = render("stablecoin_mint_hold", {
        "__ROOT_URI__": root,
        "__VAULT_URI__": vault, "__CURRENCY__": "V4T",
        "__PUBKEY__": borrower["public"],
        "__FUND__": "15000000",
        "__COLLATERAL__": "8000000",
        "__MINT__": str(MINT),
        "__ASSET__": "V4T",
    })
    debt = one(mint, borrower["secret"])[2]
    check("borrower debt", debt, MINT)

    start = node.height()
    while node.height() < start + 12:
        time.sleep(1)

    supply_before = one(call(entry["stablecoinUri"], "Stablecoin",
                             'Stablecoin!("supply", *r) | for (@x <- r) { deployId!(x) }'),
                        deployer)[1]
    repay = render("stablecoin_repay_hold", {
        "__ROOT_URI__": root,
        "__VAULT_URI__": vault, "__CURRENCY__": "V4T",
        "__PUBKEY__": borrower["public"],
        "__AMOUNT__": str(REPAY),
        "__ASSET__": "V4T",
    })
    summary = one(repay, borrower["secret"])[0]
    check("repay interest paid", summary["interestPaid"] > 0, True)
    check("repay principal paid", summary["principalPaid"] > 0, True)
    supply_after = one(call(entry["stablecoinUri"], "Stablecoin",
                            'Stablecoin!("supply", *r) | for (@x <- r) { deployId!(x) }'),
                       deployer)[1]
    check("supply falls by principal only", supply_before - supply_after,
          summary["principalPaid"])

    after = savings_info(savings, deployer)
    check("savings received the interest share", after["totalAssets"] > before["totalAssets"], True)
    check("share value rose", after["shareValueE8"] > 100_000_000, True)
    buf = buffer_info(deployer, buffer)
    check("buffer kept the retained share", buf["surplus"] > 0, True)
    check("sin remains zero without bad debt", buf["sin"], 0)

    withdraw = render("stablecoin_savings_withdraw", {
        "__ROOT_URI__": root,
        "__SAVINGS_URI__": savings,
        "__PUBKEY__": saver["public"],
        "__SHARES__": str(shares),
        "__ASSET__": "V4T",
    })
    amount = one(withdraw, saver["secret"])[0]
    check("saver withdrew more than deposited", amount > MINT, True)
    check("saver received exactly the pool assets",
          amount, after["totalAssets"])

    print(f"owner {owner_id} shares {shares}")
    print(f"savings before {before} after {after} buffer {buf}")
    print(f"withdrawn {amount} (deposit {MINT}, yield {amount - MINT})")
    print("unit_savings: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
