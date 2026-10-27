#!/usr/bin/env python3
"""Cross-block interest split and the extended S3 identity.

Mints a stablecoin in one block, waits, repays part of the debt in a later block,
and checks that the principal burn, the unpaid-interest ledger and the PSM debt
balance:

    totalDebt + badDebt + psmDebt == supply + totalAccruedInterest
"""

from __future__ import annotations

import json
import os
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
from unit_v3 import call, one  # noqa: E402
import unit_v3 as uv  # noqa: E402
uv.PHLO = 2_000_000

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"
SCENARIOS = ROOT / "harness" / "scenarios"
MINT = 100_000_000
REPAY = 99_000_000


def render(name: str, values: dict[str, str]) -> str:
    text = (SCENARIOS / f"{name}.rho").read_text()
    for key, value in values.items():
        text = text.replace(key, value)
    return minify(text)


def identity(totals: dict, psm_debt: int, supply: int) -> bool:
    return (
        totals["totalDebt"] + totals["badDebt"] + psm_debt
        == supply + totals["totalAccruedInterest"]
    )


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    registry = state["currency_registry_uri"]
    oracle = state["oracle_registry_uri"]
    secret = keys["deployer"]["secret"]

    set_price(keys, feed_uri(keys, root, oracle, "REV", [5_000_000] * 3), "REV", 5_000_000)
    set_price(keys, feed_uri(keys, root, oracle, "V4T", [66_666] * 3), "V4T", 66_666)

    entry = one(
        call(
            registry,
            "CurrencyRegistry",
            'CurrencyRegistry!("currency", "V4T", *r) | for (@x <- r) { deployId!(x) }',
        ),
        secret,
    )[1]
    vault = entry["vaultUri"]
    stablecoin = entry["stablecoinUri"]
    psm = entry["psmUri"]
    name = os.environ.get("INTEREST_KEY", "key16")
    owner = keys[name]
    owner["name"] = name
    for _ in range(6):
        request = urllib.request.Request(
            "http://localhost:40403/api/v1/faucet",
            data=json.dumps({"address": owner["address"]}).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10):
                pass
        except urllib.error.HTTPError:
            pass
        time.sleep(1)

    mint = render(
        "stablecoin_mint_hold",
        {
            "__ROOT_URI__": root,
            "__VAULT_URI__": vault,
            "__PUBKEY__": owner["public"],
            "__FUND__": "20000000",
            "__COLLATERAL__": "10000000",
            "__MINT__": str(MINT),
        },
    )
    debt = one(mint, owner["secret"])[2]
    assert debt == MINT, debt

    start = node.height()
    while node.height() < start + 12:
        time.sleep(1)

    repay = render(
        "stablecoin_repay_hold",
        {
            "__ROOT_URI__": root,
            "__VAULT_URI__": vault,
            "__PUBKEY__": owner["public"],
            "__AMOUNT__": str(REPAY),
        },
    )
    repaid = one(repay, owner["secret"])[0]
    assert repaid["debt"] > 1_000_000, repaid
    assert repaid["repaid"] == REPAY, repaid

    totals = one(
        call(
            vault,
            "VaultBook",
            'VaultBook!("totals", *r) | for (@x <- r) { deployId!(x) }',
        ),
        secret,
    )[1]
    supply = one(
        call(
            stablecoin,
            "Stablecoin",
            'Stablecoin!("supply", *r) | for (@x <- r) { deployId!(x) }',
        ),
        secret,
    )[1]
    psm_debt = one(
        call(
            psm,
            "PegStabilityModule",
            'PegStabilityModule!("debt", *r) | for (@x <- r) { deployId!(x) }',
        ),
        secret,
    )[1]

    print("totals", totals)
    print("supply", supply, "psmDebt", psm_debt)
    if not identity(totals, psm_debt, supply):
        raise SystemExit("extended S3 identity failed")
    print("unit_interest: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
