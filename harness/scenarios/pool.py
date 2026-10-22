#!/usr/bin/env python3
"""Phase-4 acceptance: seed rNGN/rKES via the CDP, add liquidity, swap, remove."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "harness" / "scenarios"))
import deploy as node  # noqa: E402
import oracle  # noqa: E402
import vault as v  # noqa: E402

MANIFEST = ROOT / "deployments" / "devnet.json"; KEYS = ROOT / ".devnet" / "keys.json"

def run_as(term, key="deployer", phlo=30_000_000):
    keys = json.loads(KEYS.read_text())
    did = node.deploy(term, keys[key]["secret"], phlo_limit=phlo)
    return node.deploy_result(did, timeout=240)

def main() -> int:
    manifest = json.loads(MANIFEST.read_text()); v.manifest = manifest; oracle.manifest = manifest
    factory = manifest["account_factory_uri"]; directory = manifest["directory_uri"]
    checks = []
    def check(name, ok, detail=""):
        checks.append((name, ok, detail)); print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    h = node.height()
    for cur, price in (("REV", 5000000), ("NGN", 66666), ("KES", 769230)):
        for i in range(3): oracle.submit(cur, price, h, i)

    # Fund the Account with 20 REV.
    r = run_as(v.render("account_deposit.rho", FACTORY_URI=factory, AMOUNT=2_000_000_000))
    check("account funded with 20 REV", 2_000_000_000 in v.ints(r), f"{v.ints(r)}")
    # NGN vault: 8 REV collateral, 300 NGN debt.
    check("open NGN vault", v.bools(run_as(v.render("account_open_vault.rho", FACTORY_URI=factory, CURRENCY="NGN")))[:1] == [True])
    r = run_as(v.render("account_collateral.rho", FACTORY_URI=factory, CURRENCY="NGN", AMOUNT=800_000_000))
    check("NGN collateral", 800_000_000 in v.ints(r), f"{v.ints(r)}")
    r = run_as(v.render("account_borrow.rho", FACTORY_URI=factory, CURRENCY="NGN", AMOUNT=30_000_000_000))
    check("borrow 300 NGN", 30_000_000_000 in v.ints(r), f"{v.ints(r)}")
    # KES vault: 10 REV collateral, 30 KES debt.
    check("open KES vault", v.bools(run_as(v.render("account_open_vault.rho", FACTORY_URI=factory, CURRENCY="KES")))[:1] == [True])
    r = run_as(v.render("account_collateral.rho", FACTORY_URI=factory, CURRENCY="KES", AMOUNT=1_000_000_000))
    check("KES collateral", 1_000_000_000 in v.ints(r), f"{v.ints(r)}")
    r = run_as(v.render("account_borrow.rho", FACTORY_URI=factory, CURRENCY="KES", AMOUNT=3_000_000_000))
    check("borrow 30 KES", 3_000_000_000 in v.ints(r), f"{v.ints(r)}")

    r = run_as(v.render("account_balance_asset.rho", FACTORY_URI=factory, ASSET="NGN"))
    check("NGN balance 300", 30_000_000_000 in v.ints(r), f"{v.ints(r)}")
    r = run_as(v.render("account_balance_asset.rho", FACTORY_URI=factory, ASSET="KES"))
    check("KES balance 30", 3_000_000_000 in v.ints(r), f"{v.ints(r)}")

    # Add 300 NGN + 26 KES.
    r = run_as(v.render("account_add_liquidity.rho", DIRECTORY_URI=directory, FACTORY_URI=factory,
                        BASE_AMT=30_000_000_000, QUOTE_AMT=2_600_000_000))
    ints = v.ints(r)
    check("add liquidity returns shares and LP balance", len(ints) >= 2 and ints[0] > 5_000_000_000,
          f"ints={ints} strings={v.strings(r)}")
    r = run_as(v.render("account_balance_asset.rho", FACTORY_URI=factory, ASSET="LP:NGN/KES:fpmm"))
    check("LP tokens in the Account", any(x > 5_000_000_000 for x in v.ints(r)), f"{v.ints(r)}")

    r = run_as(v.render("account_pool_swap.rho", DIRECTORY_URI=directory, FACTORY_URI=factory,
                        IN="KES", OUT="NGN", AMOUNT=100_000_000, MIN_OUT=1), phlo=40_000_000)
    ints = v.ints(r)
    check("swap 1 KES for NGN", len(ints) >= 2 and ints[0] > 1_000_000, f"ints={ints} strings={v.strings(r)}")

    r = run_as(v.render("pool_reserves.rho", DIRECTORY_URI=directory))
    ints = v.ints(r)
    check("pool reserves moved", len(ints) >= 3, f"ints={ints}")

    r = run_as(v.render("account_remove_liquidity.rho", DIRECTORY_URI=directory, FACTORY_URI=factory,
                        SHARES=1_000_000_000, MIN_BASE=0, MIN_QUOTE=0), phlo=40_000_000)
    ints = v.ints(r)
    check("remove 10 LP units", len(ints) >= 2 and ints[0] > 0, f"ints={ints} strings={v.strings(r)}")

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nphase 4 pool: {passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1

if __name__ == "__main__":
    raise SystemExit(main())
