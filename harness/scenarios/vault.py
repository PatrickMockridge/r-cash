#!/usr/bin/env python3
"""Phase-3 acceptance: rNGN CDP — oracle, collateral, borrow, health, repay, withdraw limits."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness" / "scenarios"))

import deploy as node  # noqa: E402
import oracle  # noqa: E402

SCEN = ROOT / "harness" / "scenarios"
MANIFEST = ROOT / "deployments" / "devnet.json"
KEYS = ROOT / ".devnet" / "keys.json"


def render(name: str, **subs) -> str:
    text = (SCEN / name).read_text()
    for k, v in subs.items():
        text = text.replace(f"__{k}__", str(v))
    return text


def run(term: str, phlo: int = 20_000_000):
    keys = json.loads(KEYS.read_text())
    did = node.deploy(term, keys["deployer"]["secret"], phlo_limit=phlo)
    return node.deploy_result(did, timeout=180)


def first_map(result):
    stack = [result]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            for k, x in v.items():
                if k == "ExprMap" and isinstance(x, dict):
                    return x.get("data")
                stack.append(x)
        elif isinstance(v, list):
            stack.extend(v)
    return None


def ints(result):
    out, stack = [], [result]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            for k, x in v.items():
                if k == "ExprInt":
                    out.append(x.get("data"))
                stack.append(x)
        elif isinstance(v, list):
            stack.extend(v)
    return out


def bools(result):
    out, stack = [], [result]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            for k, x in v.items():
                if k == "ExprBool":
                    out.append(x.get("data"))
                stack.append(x)
        elif isinstance(v, list):
            stack.extend(v)
    return out


def strings(result):
    out, stack = [], [result]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            for k, x in v.items():
                if k in ("ExprString", "ExprUri"):
                    out.append(x.get("data"))
                stack.append(x)
        elif isinstance(v, list):
            stack.extend(v)
    return out


def main() -> int:
    global manifest
    manifest = json.loads(MANIFEST.read_text())
    oracle.manifest = manifest
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    h = node.height()
    for cur, price in (("REV", 5000000), ("NGN", 66666), ("KES", 769230)):
        for i in range(3):
            check(f"oracle {cur} reporter {i}", oracle.submit(cur, price, h, i) == [True])

    # Fund the deployer Account with 2 REV.
    s, i = [], []
    r = run(render("account_deposit.rho", FACTORY_URI=manifest["account_factory_uri"],
                   AMOUNT=200_000_000))
    check("account funded with 2 REV", 200_000_000 in ints(r), f"ints={ints(r)}")

    r = run(render("account_open_vault.rho", FACTORY_URI=manifest["account_factory_uri"],
                   CURRENCY="NGN"))
    check("open rNGN vault", bools(r)[:1] == [True], f"bools={bools(r)}")

    r = run(render("account_collateral.rho", FACTORY_URI=manifest["account_factory_uri"],
                   CURRENCY="NGN", AMOUNT=100_000_000))
    m = first_map(r) or {}
    coll = (m.get("collateral") or {}).get("ExprInt", {}).get("data")
    check("deposit 1 REV collateral", coll == 100_000_000, f"map={m}")

    r = run(render("account_borrow.rho", FACTORY_URI=manifest["account_factory_uri"],
                   CURRENCY="NGN", AMOUNT=3_000_000_000))
    m = first_map(r) or {}
    debt = (m.get("debt") or {}).get("ExprInt", {}).get("data")
    check("borrow 30 rNGN", debt == 3_000_000_000, f"map={m}")

    r = run(render("account_balance_asset.rho", FACTORY_URI=manifest["account_factory_uri"],
                   ASSET="NGN"))
    check("rNGN in the Account", 3_000_000_000 in ints(r), f"ints={ints(r)}")

    r = run(render("account_vault_info.rho", FACTORY_URI=manifest["account_factory_uri"],
                   CURRENCY="NGN"))
    m = first_map(r) or {}
    health = (m.get("health") or {}).get("ExprBool", {}).get("data")
    vdebt = (m.get("debt") or {}).get("ExprInt", {}).get("data")
    check("vault healthy at 250%", health is True and vdebt >= 3_000_000_000,
          f"map={m}")

    r = run(render("account_borrow.rho", FACTORY_URI=manifest["account_factory_uri"],
                   CURRENCY="NGN", AMOUNT=2_000_000_000))
    check("over-MCR borrow refused", bools(r)[:1] == [False], f"bools={bools(r)} strings={strings(r)}")

    r = run(render("account_repay.rho", FACTORY_URI=manifest["account_factory_uri"],
                   CURRENCY="NGN", AMOUNT=1_000_000_000))
    m = first_map(r) or {}
    repaid_debt = (m.get("debt") or {}).get("ExprInt", {}).get("data")
    check("repay 10 rNGN", repaid_debt is not None and repaid_debt <= 2_000_000_100,
          f"map={m}")

    r = run(render("account_withdraw_collateral.rho", FACTORY_URI=manifest["account_factory_uri"],
                   CURRENCY="NGN", AMOUNT=50_000_000))
    check("over-MCR collateral withdrawal refused", bools(r)[:1] == [False],
          f"bools={bools(r)} strings={strings(r)}")

    r = run(render("account_withdraw_collateral.rho", FACTORY_URI=manifest["account_factory_uri"],
                   CURRENCY="NGN", AMOUNT=30_000_000))
    check("healthy collateral withdrawal succeeds", bools(r)[:1] == [True],
          f"bools={bools(r)} strings={strings(r)}")

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nphase 3 vault: {passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
