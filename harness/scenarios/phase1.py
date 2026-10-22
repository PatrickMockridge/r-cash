#!/usr/bin/env python3
"""Phase-1 acceptance: Directory bootstrap/lock, two Accounts, owner auth, deposit/withdraw.

Run against the running devnet after `make bootstrap` (the bootstrap writes deployments/devnet.json).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import deploy as node  # noqa: E402

SCEN = ROOT / "harness" / "scenarios"
MANIFEST = ROOT / "deployments" / "devnet.json"
KEYS = ROOT / ".devnet" / "keys.json"
DEPLOYER = "deployer"


def walk(value, out):
    if isinstance(value, dict):
        for k, v in value.items():
            if k.startswith("Expr") and isinstance(v, dict):
                out.append((k, v.get("data")))
                walk(v.get("data"), out)
            else:
                walk(v, out)
    elif isinstance(value, list):
        for v in value:
            walk(v, out)
    return out


def vals(result):
    return walk(result, [])


def ints(result):
    return [v for k, v in vals(result) if k == "ExprInt"]


def bools(result):
    return [v for k, v in vals(result) if k == "ExprBool"]


def strings(result):
    return [str(v) for k, v in vals(result) if k in ("ExprString", "ExprUri")]


def render(name: str, **subs) -> str:
    text = (SCEN / name).read_text()
    for k, v in subs.items():
        text = text.replace(f"__{k}__", str(v))
    return text


def run(term: str, key: str, phlo: int = 5_000_000):
    keys = json.loads(KEYS.read_text())
    did = node.deploy(term, keys[key]["secret"], phlo_limit=phlo)
    return node.deploy_result(did, timeout=180)


def deposit(key: str, amount: int):
    r = run(render("account_deposit.rho", FACTORY_URI=manifest["account_factory_uri"],
                   AMOUNT=amount), key, phlo=8_000_000)
    return strings(r), ints(r)


def withdraw(key: str, amount: int):
    r = run(render("account_withdraw.rho", FACTORY_URI=manifest["account_factory_uri"],
                   AMOUNT=amount), key, phlo=8_000_000)
    return strings(r), ints(r)


def balance(key: str):
    r = run(render("account_balance.rho", FACTORY_URI=manifest["account_factory_uri"]),
            key, phlo=3_000_000)
    return strings(r), bools(r), ints(r)


def unauthorized(attacker: str, victim_pubkey: str):
    r = run(render("account_unauthorized.rho", FACTORY_URI=manifest["account_factory_uri"],
                   VICTIM_PUBKEY=victim_pubkey), attacker, phlo=2_000_000)
    return bools(r), strings(r)


def directory_check():
    r = run(render("directory_check.rho", DIRECTORY_URI=manifest["directory_uri"]),
            DEPLOYER, phlo=3_000_000)
    return strings(r), bools(r)


def main() -> int:
    global manifest
    manifest = json.loads(MANIFEST.read_text())
    keys = json.loads(KEYS.read_text())
    checks: list[tuple[str, bool, str]] = []

    def check(name, ok, detail):
        checks.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # 1. Directory resolves the accounts component and is locked.
    s, b = directory_check()
    got_uri = any(u == manifest["account_factory_uri"] for u in s)
    locked = False in b
    check("Directory resolves component:accounts", got_uri, f"strings={s}")
    check("Directory refuses registration after lock", locked, f"bools={b}")

    # 2. Deployer account: balance, deposit, withdraw, balance.
    _, b0, i0 = balance(DEPLOYER)
    before = i0[-1] if b0 and b0[-1] and i0 else 0
    s, i = deposit(DEPLOYER, 5_000_000)
    after_dep = i[-1] if i else None
    check("deployer deposit increases balance by 5,000,000",
          after_dep == before + 5_000_000,
          f"before={before} after={after_dep}")

    s, i = withdraw(DEPLOYER, 2_000_000)
    purse_after = i[-1] if i else None
    check("withdraw returns a 2,000,000 payment", purse_after == 2_000_000,
          f"payment={purse_after}")

    _, b2, i2 = balance(DEPLOYER)
    final = i2[-1] if i2 else None
    check("account balance is before + 3,000,000", final == before + 3_000_000,
          f"final={final}")

    # 3. A second key has its own account.
    _, b3, i3 = balance("sender")
    sender_before = i3[-1] if b3 and b3[-1] and i3 else 0
    s3, i4 = deposit("sender", 2_000_000)
    sender_after = i4[-1] if i4 else None
    check("sender has an independent account",
          sender_after == sender_before + 2_000_000,
          f"before={sender_before} after={sender_after} owner={s3[-1] if s3 else None}")

    # 4. The sender cannot withdraw from the deployer's account.
    b4, s4 = unauthorized("sender", keys[DEPLOYER]["public"])
    check("unauthorised withdrawal refused",
          b4[:1] == [False] and "not owner" in s4,
          f"bools={b4} strings={s4}")

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nphase 1: {passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
