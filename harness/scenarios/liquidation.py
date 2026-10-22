#!/usr/bin/env python3
"""Phase-3b: a REV price drop makes a vault liquidatable; another account liquidates it."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness" / "scenarios"))

import deploy as node  # noqa: E402
import oracle  # noqa: E402
import vault as v  # noqa: E402

MANIFEST = ROOT / "deployments" / "devnet.json"
KEYS = ROOT / ".devnet" / "keys.json"


def run_as(term: str, key: str, phlo: int = 10_000_000):
    keys = json.loads(KEYS.read_text())
    did = node.deploy(term, keys[key]["secret"], phlo_limit=phlo)
    return node.deploy_result(did, timeout=180)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    v.manifest = manifest
    oracle.manifest = manifest
    keys = json.loads(KEYS.read_text())
    factory = manifest["account_factory_uri"]
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    h = node.height()
    for cur, price in (("REV", 5000000), ("NGN", 66666), ("KES", 769230)):
        for i in range(3):
            oracle.submit(cur, price, h, i)

    # Deployer: 1 REV collateral, 30 rNGN debt (liquidator liquidity).
    r = run_as(v.render("account_deposit.rho", FACTORY_URI=factory, AMOUNT=200_000_000), "deployer")
    check("deployer funded", 200_000_000 in v.ints(r), f"{v.ints(r)}")
    check("deployer vault", v.bools(run_as(v.render("account_open_vault.rho", FACTORY_URI=factory, CURRENCY="NGN"), "deployer"))[:1] == [True])
    r = run_as(v.render("account_collateral.rho", FACTORY_URI=factory, CURRENCY="NGN", AMOUNT=100_000_000), "deployer")
    check("deployer collateral", 100_000_000 in v.ints(r), f"{v.ints(r)}")
    r = run_as(v.render("account_borrow.rho", FACTORY_URI=factory, CURRENCY="NGN", AMOUNT=3_000_000_000), "deployer")
    check("deployer borrow", 3_000_000_000 in v.ints(r), f"{v.ints(r)}")

    # Sender: 0.25 REV collateral, 7 rNGN debt.
    r = run_as(v.render("account_deposit.rho", FACTORY_URI=factory, AMOUNT=25_000_000), "sender")
    check("sender funded", 25_000_000 in v.ints(r), f"{v.ints(r)}")
    check("sender vault", v.bools(run_as(v.render("account_open_vault.rho", FACTORY_URI=factory, CURRENCY="NGN"), "sender"))[:1] == [True])
    r = run_as(v.render("account_collateral.rho", FACTORY_URI=factory, CURRENCY="NGN", AMOUNT=20_000_000), "sender")
    check("sender collateral", 20_000_000 in v.ints(r), f"{v.ints(r)}")
    r = run_as(v.render("account_borrow.rho", FACTORY_URI=factory, CURRENCY="NGN", AMOUNT=700_000_000), "sender")
    check("sender borrow", 700_000_000 in v.ints(r), f"{v.ints(r)}")
    sender_owner = keys["sender"]["address"]

    r = run_as(v.render("account_vault_info.rho", FACTORY_URI=factory, CURRENCY="NGN"), "sender")
    m = v.first_map(r) or {}
    check("sender healthy before drop",
          (m.get("health") or {}).get("ExprBool", {}).get("data") is True, f"{m}")
    debt_before = (m.get("debt") or {}).get("ExprInt", {}).get("data")
    coll_before = (m.get("collateral") or {}).get("ExprInt", {}).get("data")

    # Drop REV from 0.05 to 0.04 USD at the current height.
    h2 = node.height()
    for i in range(3):
        ok = oracle.submit("REV", 4_000_000, h2, i)
        check(f"REV drop reporter {i}", ok == [True], f"{ok}")
    rev = oracle.get("REV")
    check("REV feed fresh after drop", rev["fresh"] is True, f"{rev}")
    r = run_as(v.render("account_vault_info.rho", FACTORY_URI=factory, CURRENCY="NGN"), "sender")
    m = v.first_map(r) or {}
    check("sender liquidatable after drop",
          (m.get("liquidatable") or {}).get("ExprBool", {}).get("data") is True, f"{m}")

    # Liquidator repays 3.5 rNGN (50% close factor) and receives REV.
    r = run_as(v.render("account_liquidate.rho", FACTORY_URI=factory, CURRENCY="NGN",
                        VICTIM=sender_owner, AMOUNT=350_000_000), "deployer", phlo=20_000_000)
    check("liquidate call succeeds", v.bools(r)[:1] == [True], f"bools={v.bools(r)} strings={v.strings(r)}")

    r = run_as(v.render("account_vault_info.rho", FACTORY_URI=factory, CURRENCY="NGN"), "sender")
    m = v.first_map(r) or {}
    debt = (m.get("debt") or {}).get("ExprInt", {}).get("data")
    coll = (m.get("collateral") or {}).get("ExprInt", {}).get("data")
    check("victim debt reduced by 3.5 rNGN",
          debt is not None and debt_before is not None and debt <= debt_before - 340_000_000,
          f"before={debt_before} after={debt}")
    check("victim collateral seized",
          coll is not None and coll_before is not None and coll < coll_before,
          f"before={coll_before} after={coll}")

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nphase 3b liquidation: {passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
