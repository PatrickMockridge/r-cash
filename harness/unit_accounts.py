#!/usr/bin/env python3
"""Exercise v0.4 accounts and purses.

The owner key creates an account, deposits REV through the deposit facet,
reads the balance, withdraws, and resolves a listed stablecoin to an empty
purse. A second deploy signed by a different key obtains the same account
capability and is refused by AccountGate.

Run `make unit-stablecoin` first: the V4T balance check needs a listed currency.

Usage:
    python3 harness/unit_accounts.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

from minify_rho import minify  # noqa: E402
from unit_v3 import call, check, faucet_top_up, one  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"
SCENARIOS = ROOT / "harness" / "scenarios"
FUND = 20_000_000
DEPOSIT = 10_000_000
WITHDRAW = 4_000_000


def render_scenario(name: str, values: dict) -> str:
    text = (SCENARIOS / name).read_text()
    for key, value in values.items():
        text = text.replace(key, value)
    return minify(text)


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    registry = state["currency_registry_uri"]

    listed = one(call(registry, "CurrencyRegistry",
                      'CurrencyRegistry!("currency", "V4T", *r) | '
                      "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    if not listed[0]:
        raise AssertionError("V4T is not listed; run make unit-stablecoin first")

    owner = keys["business"]
    faucet_top_up(owner["address"])
    faucet_top_up(keys["ramp"]["address"])
    owner_term = render_scenario("account_purse.rho", {
        "__ROOT_URI__": root,
        "__PUBKEY__": owner["public"],
        "__FUND__": str(FUND),
        "__DEPOSIT__": str(DEPOSIT),
        "__WITHDRAW__": str(WITHDRAW),
    })
    result = one(owner_term, owner["secret"])
    owner_id, after_deposit, after_withdraw, stablecoin_balance = result
    check("owner address returned", owner_id, owner["address"])
    check("deposit credited", after_deposit, DEPOSIT)
    check("withdraw debited", after_withdraw, DEPOSIT - WITHDRAW)
    check("stablecoin purse resolved empty", stablecoin_balance, (True, 0))
    print(f"account: {owner_id}")

    foreign_term = render_scenario("account_foreign.rho", {
        "__ROOT_URI__": root,
        "__OWNER_PUB__": owner["public"],
    })
    check("foreign deployer refused",
          one(foreign_term, keys["ramp"]["secret"]), "balance-refused")

    print("unit_accounts: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
