#!/usr/bin/env python3
"""Drive the v0.3 kernel components in isolation on a devnet.

Each test is a small deploy that resolves one component URI, calls an arm and
emits a value through `rho:rchain:deployId`. The script checks the decoded value
and exits non-zero on the first mismatch.

Usage:
    python3 harness/unit_v3.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import deploy as node  # noqa: E402
import sign_payload  # noqa: E402

STATE = ROOT / ".devnet" / "v3-install.json"
KEYS = ROOT / ".devnet" / "keys.json"
PHLO = 10_000_000


def decode(value):
    if isinstance(value, list):
        return [decode(item) for item in value]
    if isinstance(value, dict):
        if "ExprString" in value:
            return value["ExprString"]["data"]
        if "ExprUri" in value:
            return value["ExprUri"]["data"]
        if "ExprInt" in value:
            return int(value["ExprInt"]["data"])
        if "ExprBool" in value:
            return bool(value["ExprBool"]["data"])
        if "ExprTuple" in value:
            return tuple(decode(item) for item in value["ExprTuple"]["data"])
        if "ExprList" in value:
            return [decode(item) for item in value["ExprList"]["data"]]
        if "ExprSet" in value:
            return [decode(item) for item in value["ExprSet"]["data"]]
        if "ExprMap" in value:
            data = value["ExprMap"]["data"]
            if isinstance(data, dict):
                return {key: decode(item) for key, item in data.items()}
            return {
                decode(entry["key"]): decode(entry["value"])
                for entry in data
            }
        if "ExprByteArray" in value:
            return bytes.fromhex(value["ExprByteArray"]["data"])
        return {key: decode(item) for key, item in value.items()}
    return value


def faucet_top_up(address: str) -> None:
    """Drip 0.3 REV when the finalized balance is below one drip.

    The faucet is idempotent below 30,000,000 drops; a suite that funds 15-20m
    from a key needs the precharge reservation on top, so top up before it runs.
    """
    import time
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        "http://localhost:40403/api/v1/faucet",
        data=json.dumps({"address": address}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            time.sleep(2.5)
    except urllib.error.HTTPError:
        pass


def deploy_call(term: str, secret: str) -> list:
    # A deploy submitted immediately after the installer can see a stale balance:
    # the previous deploy's phlo refund lands one finalization late. Retry that
    # one error; every other failure is real.
    for attempt in range(3):
        deploy_id = node.deploy(term, secret, phlo_limit=PHLO)
        variant, payload = node.wait_processed(deploy_id, timeout=180)
        error = str(payload.get("deployError") or "")
        if variant == "processedwitherror" and "insufficient funds" in error and attempt < 2:
            time.sleep(3)
            continue
        break
    if variant != "processedwithsuccess":
        raise AssertionError(f"{variant}: {json.dumps(payload)[:2000]}")
    return decode(payload.get("deployResult"))


def one(term: str, secret: str):
    result = deploy_call(term, secret)
    if not result:
        raise AssertionError("empty deploy result")
    return result[0]


def call(uri: str, binding: str, body: str) -> str:
    return (
        "new rl(`rho:registry:lookup`), ch, r, "
        "deployId(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{uri}`, *ch) |\n"
        f"  for ({binding} <- ch) {{ {body} }}\n"
        "}"
    )


def check(label: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"ok {label}")


def ok_or_reason(call_expr: str) -> str:
    return (
        f"{call_expr} |\n"
        "  for (@x <- r) {\n"
        "    match x {\n"
        '      (true, Nil) => deployId!("ok")\n'
        "      (false, why) => deployId!(why)\n"
        "    }\n"
        "  }"
    )


def main() -> int:
    state = json.loads(STATE.read_text())
    keys = json.loads(KEYS.read_text())
    secret = keys["deployer"]["secret"]
    root = state["root_uri"]

    check(
        "Root.resolve clock",
        one(call(root, "Root",
                 'Root!("resolve", "component:clock", 1, *r) |\n'
                 "  for (@x <- r) { deployId!(x) }"), secret),
        (True, state["clock_uri"], 1),
    )
    check(
        "Root.resolve unknown",
        one(call(root, "Root",
                 'Root!("resolve", "component:nope", 1, *r) |\n'
                 "  for (@x <- r) { deployId!(x) }"), secret),
        (False, "unknown component"),
    )
    check(
        "Root.keys",
        one(call(root, "Root",
                 'Root!("keys", *r) |\n'
                 "  for (@x <- r) {\n"
                 "    match x {\n"
                 '      (true, ks) => deployId!(ks.contains("component:clock") && ks.contains("component:governor"))\n'
                 "      _ => deployId!(false)\n"
                 "    }\n"
                 "  }"), secret),
        True,
    )
    check(
        "Clock.now",
        one(call(state["clock_uri"], "Clock",
                 'Clock!("now", *r) |\n'
                 "  for (@h <- r) { deployId!(h > 0) }"), secret),
        True,
    )

    expected_hash = hashlib.blake2b(b"abc", digest_size=32).hexdigest()
    check(
        "Verifier.hash",
        one(call(state["verifier_uri"], "Verifier",
                 'Verifier!("hash", "abc".toUtf8Bytes(), *r) |\n'
                 f'  for (@h <- r) {{ deployId!(h == "{expected_hash}".hexToBytes()) }}'), secret),
        True,
    )

    canonical = "rcash:test:v1|1:a|2:bc"
    check(
        "Codec.canonical",
        one(call(state["codec_uri"], "Codec",
                 'Codec!("canonical", "rcash:test:v1", ["a", "bc"], *r) |\n'
                 "  for (@s <- r) { deployId!(s) }"), secret),
        canonical,
    )
    expected_codec = hashlib.blake2b(canonical.encode(), digest_size=32).hexdigest()
    check(
        "Codec.hash",
        one(call(state["codec_uri"], "Codec",
                 'Codec!("hash", "rcash:test:v1", ["a", "bc"], *r) |\n'
                 f'  for (@h <- r) {{ deployId!(h == "{expected_codec}".hexToBytes()) }}'), secret),
        True,
    )

    check(
        "Bounds.checkFeed ok",
        one(call(state["bounds_uri"], "Bounds",
                 ok_or_reason('Bounds!("checkFeed", 2, 50, 200, 1, 1000000000000, 10, 4, *r)')), secret),
        "ok",
    )
    check(
        "Bounds.checkFeed bad quorum",
        one(call(state["bounds_uri"], "Bounds",
                 ok_or_reason('Bounds!("checkFeed", 0, 50, 200, 1, 1000000000000, 10, 4, *r)')), secret),
        "quorum",
    )
    pool_ok = ('{"baseSpreadBps": 20, "skewSpreadBps": 80, "maxTradeBps": 500, '
               '"minLiquidity": 100000000, "firstDepositToleranceBps": 100, '
               '"depthFloorQuote": 100000000000, "minTicketQuote": 1000000000}')
    check(
        "Bounds.checkPool ok",
        one(call(state["bounds_uri"], "Bounds",
                 ok_or_reason(f'Bounds!("checkPool", {pool_ok}, *r)')), secret),
        "ok",
    )
    book_ok = ('{"defaultExpiryBlocks": 100, "maxExpiryBlocks": 1000, "minAmount": 1, '
               '"maxMemoBytes": 128, "maxOpIdBytes": 64, "maxStipend": 100000000}')
    check(
        "Bounds.checkBook ok",
        one(call(state["bounds_uri"], "Bounds",
                 ok_or_reason(f'Bounds!("checkBook", {book_ok}, *r)')), secret),
        "ok",
    )

    check(
        "AmmMath.value",
        one(call(state["05_amm_math_uri"], "AmmMath",
                 'AmmMath!("value", 100, 100, 100000000, *r) |\n'
                 "  for (@x <- r) { deployId!(x) }"), secret),
        200,
    )
    check(
        "AmmMath.out b2q",
        one(call(state["05_amm_math_uri"], "AmmMath",
                 'AmmMath!("out", "b2q", 10, 100000000, 0, *r) |\n'
                 "  for (@x <- r) { deployId!(x) }"), secret),
        10,
    )
    check(
        "AmmMath.shares first",
        one(call(state["05_amm_math_uri"], "AmmMath",
                 'AmmMath!("shares", 200000000, 0, 0, true, *r) |\n'
                 "  for (@x <- r) { deployId!(x) }"), secret),
        100000000,
    )

    check(
        "OracleMath.median3",
        one(call(state["07_oracle_math_uri"], "OracleMath",
                 'OracleMath!("median3", 5, 1, 3, *r) |\n'
                 "  for (@x <- r) { deployId!(x) }"), secret),
        3,
    )
    check(
        "OracleMath.rate",
        one(call(state["07_oracle_math_uri"], "OracleMath",
                 'OracleMath!("rate", 100000000, 200000000, *r) |\n'
                 "  for (@x <- r) { deployId!(x) }"), secret),
        50000000,
    )
    check(
        "OracleMath.fresh",
        one(call(state["07_oracle_math_uri"], "OracleMath",
                 'OracleMath!("fresh", 100, 101, 99, 10, 10, 10, 10, 2, 50, 200, '
                 "1, 1000000000000, *r) |\n"
                 "  for (@x <- r) {\n"
                 "    match x {\n"
                 "      (true, median, Nil) => deployId!(median == 100)\n"
                 "      (false, m, why) => deployId!(why)\n"
                 "    }\n"
                 "  }"), secret),
        True,
    )

    check(
        "Governor.admins",
        one(call(state["governor_uri"], "Governor",
                 'Governor!("admins", *r) |\n'
                 "  for (@x <- r) {\n"
                 "    match x {\n"
                 "      (true, admins, threshold) => deployId!(admins.length() == 3 && threshold == 2)\n"
                 "      _ => deployId!(false)\n"
                 "    }\n"
                 "  }"), secret),
        True,
    )

    non_installer = keys["reporter1"]["secret"]
    register_term = (
        "new rl(`rho:registry:lookup`), ch, r, "
        "deployerId(`rho:rchain:deployerId`), deployId(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{root}`, *ch) |\n"
        "  for (Root <- ch) {\n"
        '    Root!("register", "test:key", "rho:id:fake", 1, "test", *deployerId, *r) |\n'
        "    for (@x <- r) { deployId!(x) }\n"
        "  }\n"
        "}"
    )
    check("Root.register non-installer", one(register_term, non_installer),
          (False, "not installer"))

    payload = sign_payload.admin_payload("test", 1, "noop", [])
    sig1 = sign_payload.sign_payload(keys["admin1"]["secret"], payload)["signature"]
    sig2 = sign_payload.sign_payload(keys["admin2"]["secret"], payload)["signature"]
    admins = "[" + ", ".join(
        f'"{keys[n]["public"]}".hexToBytes()' for n in ["admin1", "admin2", "admin3"]
    ) + "]"

    def guard_term(sigs: str) -> str:
        body = (
            f'AdminGuard!("verify", "test", 1, "noop", "", {sigs}, {admins}, 2, *r) |\n'
            "  for (@x <- r) {\n"
            "    match x {\n"
            '      (true, Nil) => deployId!("ok")\n'
            "      (false, why) => deployId!(why)\n"
            "    }\n"
            "  }"
        )
        return call(state["admin_guard_uri"], "AdminGuard", body)

    check("AdminGuard two signatures",
          one(guard_term(f'["{sig1}".hexToBytes(), "{sig2}".hexToBytes()]'), secret), "ok")
    check("AdminGuard one signature",
          one(guard_term(f'["{sig1}".hexToBytes()]'), secret), "below threshold")

    print("unit_v3: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
