#!/usr/bin/env python3
"""Phase-2 acceptance: signed reporter prices, median/freshness, cross rate, admin 2-of-3."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import deploy as node  # noqa: E402
from sign_payload import admin_payload, oracle_payload, sign_payload  # noqa: E402

SCEN = ROOT / "harness" / "scenarios"
MANIFEST = ROOT / "deployments" / "devnet.json"
KEYS = ROOT / ".devnet" / "keys.json"
REPORTERS = ["reporter1", "reporter2", "reporter3"]
ADMINS = ["admin1", "admin2", "admin3"]


def render(name: str, **subs) -> str:
    text = (SCEN / name).read_text()
    for k, v in subs.items():
        text = text.replace(f"__{k}__", str(v))
    return text


def run(term: str, phlo: int = 5_000_000):
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


def submit(currency: str, price: int, height: int, index: int):
    keys = json.loads(KEYS.read_text())
    reporter = REPORTERS[index]
    sig = sign_payload(keys[reporter]["secret"], oracle_payload(currency, price, height))["signature"]
    r = run(render("oracle_submit.rho", ORACLE_URI=manifest["oracle_uri"], CURRENCY=currency,
                   PRICE=price, HEIGHT=height, INDEX=index, PUB=keys[reporter]["public"], SIG=sig))
    return bools(r)


def get(currency: str):
    r = run(render("oracle_get.rho", ORACLE_URI=manifest["oracle_uri"], CURRENCY=currency),
            phlo=4_000_000)
    m = first_map(r) or {}
    return {
        "price": (m.get("price") or {}).get("ExprInt", {}).get("data"),
        "height": (m.get("height") or {}).get("ExprInt", {}).get("data"),
        "fresh": (m.get("fresh") or {}).get("ExprBool", {}).get("data"),
        "reason": (m.get("reason") or {}).get("ExprString", {}).get("data"),
        "raw": r,
    }


def get_pair(base: str, quote: str):
    r = run(render("oracle_pair.rho", ORACLE_URI=manifest["oracle_uri"], BASE=base, QUOTE=quote),
            phlo=4_000_000)
    m = first_map(r) or {}
    return {
        "rate": (m.get("rate") or {}).get("ExprInt", {}).get("data"),
        "fresh": (m.get("fresh") or {}).get("ExprBool", {}).get("data"),
        "reason": (m.get("reason") or {}).get("ExprString", {}).get("data"),
        "raw": r,
    }


def admin(nonce: int, args: list, signers: list[str]):
    keys = json.loads(KEYS.read_text())
    payload = admin_payload("oracle", nonce, "setParams", args)
    sigs = [sign_payload(keys[s]["secret"], payload)["signature"] for s in signers]
    args_lit = "[" + ", ".join(str(a) for a in args) + "]"
    sigs_lit = "[" + ", ".join(f'"{s}".hexToBytes()' for s in sigs) + "]"
    r = run(render("oracle_admin.rho", ORACLE_URI=manifest["oracle_uri"], NONCE=nonce,
                   ACTION="setParams", ARGS=args_lit, SIGS=sigs_lit))
    return bools(r)


def main() -> int:
    global manifest
    manifest = json.loads(MANIFEST.read_text())
    checks = []

    def check(name, ok, detail):
        checks.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    h = node.height()
    ngn_prices = [66600, 66666, 66700]
    for i, p in enumerate(ngn_prices):
        check(f"reporter {i} submits NGN", submit("NGN", p, h, i) == [True], f"price={p}")
    for cur, p in (("KES", 769230), ("REV", 5000000)):
        for i in range(3):
            check(f"reporter {i} submits {cur}", submit(cur, p, h, i) == [True], f"price={p}")

    ngn = get("NGN")
    check("NGN median is 66,666 and fresh", ngn["price"] == 66666 and ngn["fresh"] is True,
          f"{ngn}")
    kes = get("KES")
    check("KES is fresh", kes["fresh"] is True, f"{kes}")
    pair = get_pair("NGN", "KES")
    expected = (66666 * 100_000_000) // 769230
    check("NGN/KES cross rate", pair["fresh"] is True and abs((pair["rate"] or 0) - expected) <= 1,
          f"rate={pair['rate']} expected={expected}")

    # Unauthorized: reporter1's key/signature at index 1 (reporter2's slot).
    keys = json.loads(KEYS.read_text())
    bad_sig = sign_payload(keys["reporter1"]["secret"], oracle_payload("NGN", 70000, h))["signature"]
    bad = run(render("oracle_submit.rho", ORACLE_URI=manifest["oracle_uri"], CURRENCY="NGN",
                     PRICE=70000, HEIGHT=h, INDEX=1, PUB=keys["reporter1"]["public"], SIG=bad_sig))
    check("reporters cannot use another reporter's index", bools(bad) == [False], f"{bools(bad)}")

    # Admin: 2-of-3 succeeds, replay fails, 1-of-3 fails.
    params = [2, 50, 200, 1, 1000000000000]
    nonce = int(time.time())
    check("2-of-3 admin setParams", admin(nonce, params, ["admin1", "admin2"]) == [True], "")
    check("replayed admin nonce rejected", admin(nonce, params, ["admin1", "admin2"]) == [False], "")
    check("1-of-3 admin rejected", admin(nonce + 1, params, ["admin1"]) == [False], "")

    # Staleness: set maxAge to 0, then the existing prices are stale.
    check("set maxAge=0", admin(nonce + 2, [2, 0, 200, 1, 1000000000000], ["admin1", "admin2"]) == [True], "")
    stale = get("NGN")
    check("stale feed reports fresh=false", stale["fresh"] is False, f"{stale}")
    check("restore maxAge=50", admin(nonce + 3, params, ["admin1", "admin2"]) == [True], "")

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nphase 2 oracle: {passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
