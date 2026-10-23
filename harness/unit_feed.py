#!/usr/bin/env python3
"""Exercise the v0.3 OracleFeed in isolation on a devnet.

Deploys one feed for a test currency signed by the deployer, submits three reporter prices,
activates it, reads it back, and pauses it through Governor + AdminGuard.
OracleRegistry binding is tested separately once the registry is installed.

Usage:
    python3 harness/unit_feed.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import deploy as node  # noqa: E402
import sign_payload  # noqa: E402
from install_v3 import render  # noqa: E402
from unit_v3 import call, check, decode, deploy_call, one, ok_or_reason  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"
PHLO = 40_000_000


def canonical(schema: str, values: list[str]) -> str:
    return schema + "|" + "|".join(f"{len(v)}:{v}" for v in values)


def blake2b256(text: str) -> str:
    return hashlib.blake2b(text.encode(), digest_size=32).hexdigest()


def deploy_feed(term: str, secret: str):
    deploy_id = node.deploy(term, secret, phlo_limit=PHLO)
    variant, payload = node.wait_processed(deploy_id, timeout=300)
    if variant != "processedwithsuccess":
        raise AssertionError(f"feed deploy {variant}: {json.dumps(payload)[:3000]}")
    block = payload.get("block") or {}
    if block.get("blockHash"):
        node.wait_finalized(block["blockHash"])
    result = decode(payload.get("deployResult"))
    if not result:
        raise AssertionError("feed deploy returned no result")
    return result[0]


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    secret = keys["deployer"]["secret"]
    sponsor = keys["sponsor"]["public"]
    reporters = [keys[n]["public"] for n in ("reporter1", "reporter2", "reporter3")]
    feed_id = "NGT-feed-test-1"
    currency = "NGT"
    policy_values = [
        currency, reporters[0], reporters[1], reporters[2], sponsor,
        "2", "50", "200", "1", "1000000000000", "1", "3",
    ]
    policy_hash = blake2b256(canonical("rcash:oracle-policy:v3", policy_values))
    reporters_rholang = "[" + ", ".join(f'"{k}"' for k in reporters) + "]"

    term = render("31_feed", {
        "__ROOT_URI__": root,
        "__CURRENCY__": currency,
        "__FEED_ID__": feed_id,
        "__REPORTERS__": reporters_rholang,
        "__SPONSOR_PUB__": sponsor,
        "__POLICY_HASH__": policy_hash,
        "__QUORUM__": "2",
        "__MAX_AGE__": "50",
        "__MAX_SPREAD__": "200",
        "__MIN_PRICE__": "1",
        "__MAX_PRICE__": "1000000000000",
        "__TRIAL_BLOCKS__": "1",
        "__TRIAL_MIN_SUBMITS__": "3",
    })
    feed = deploy_feed(term, secret)
    uri, att_reply = feed
    attest = att_reply[1]
    check("feed deploy attestation", attest.get("feedId"), feed_id)
    check("feed deploy policy hash", attest.get("policyHash"), policy_hash)
    print(f"feed uri: {uri}")

    info = one(call(uri, "OracleFeed",
                    'OracleFeed!("info", *r) | for (@x <- r) { deployId!(x) }'), secret)[1]
    check("feed info active", info.get("active"), False)
    check("feed info reporters", len(info.get("reporters")), 3)

    height = node.height()
    prices = [100, 101, 99]
    for index, price in enumerate(prices):
        payload = f"rcash:oracle-submit:v3|{feed_id}|{currency}|{index}|{price}|{height}"
        sig = sign_payload.sign_payload(keys[f"reporter{index + 1}"]["secret"],
                                        payload.encode())["signature"]
        body = (
            f'OracleFeed!("submit", {index}, {price}, {height}, '
            f'"{reporters[index]}", "{sig}".hexToBytes(), *r) |\n'
            "  for (@x <- r) {\n"
            "    match x {\n"
            '      (true, Nil) => deployId!("ok")\n'
            "      (false, why) => deployId!(why)\n"
            "    }\n"
            "  }"
        )
        check(f"feed submit {index}",
              one(call(uri, "OracleFeed", body), secret), "ok")

    height_after = node.height()
    check("feed advanced", height_after > height, True)

    activation = one(call(uri, "OracleFeed",
                          ok_or_reason('OracleFeed!("activate", *r)')), secret)
    check("feed activate", activation, "ok")

    reading = one(call(uri, "OracleFeed",
                       'OracleFeed!("get", *r) | for (@x <- r) { deployId!(x) }'), secret)[1]
    check("feed get fresh", reading.get("fresh"), True)
    check("feed get price", reading.get("price"), 100)

    registry = state.get("oracle_registry_uri")
    if registry:
        bind_payload = (
            f"rcash:feed-bind:v3|{currency}|{feed_id}|{uri}|{policy_hash}|{sponsor}"
        )
        bind_sig = sign_payload.sign_payload(keys["sponsor"]["secret"],
                                             bind_payload.encode())["signature"]
        def bind_term(sig: str, feed_uri: str = uri, feed: str = feed_id) -> str:
            return (
                "new rl(`rho:registry:lookup`), ch, r, "
                "deployerId(`rho:rchain:deployerId`), "
                "deployId(`rho:rchain:deployId`) in {\n"
                f"  rl!(`{registry}`, *ch) |\n"
                "  for (Registry <- ch) {\n"
                f'    Registry!("registerFeed", "{currency}", "{feed_uri}", "{feed}", '
                f'"{policy_hash}", "{sponsor}", "{sig}".hexToBytes(), '
                "*deployerId, *r) |\n"
                "    for (@x <- r) {\n"
                "      match x {\n"
                '        (true, Nil) => deployId!("ok")\n'
                "        (false, why) => deployId!(why)\n"
                "      }\n"
                "    }\n"
                "  }\n"
                "}"
            )
        check("feed bind", one(bind_term(bind_sig), keys["sponsor"]["secret"]), "ok")
        entry = one(call(registry, "OracleRegistry",
                         f'OracleRegistry!("feedEntry", "{currency}", *r) | '
                         "for (@x <- r) { deployId!(x) }"), secret)[1]
        check("feed registry uri", entry.get("uri"), uri)
        check("feed duplicate bind",
              one(bind_term(bind_sig), keys["sponsor"]["secret"]), "duplicate")
        check("feed bind bad deployer",
              one(bind_term(bind_sig), secret), "bad sponsor")
        bad_sig = sign_payload.sign_payload(keys["admin1"]["secret"],
                                            bind_payload.encode())["signature"]
        check("feed bind bad signature",
              one(bind_term(bad_sig), keys["sponsor"]["secret"]),
              "bad sponsor signature")

    # Pause through Governor and AdminGuard, then observe the freshness reason.
    admin_nonce = node.height()
    payload = sign_payload.admin_payload(f"oracle:{currency}", admin_nonce, "setPaused", ["true"])
    sig1 = sign_payload.sign_payload(keys["admin1"]["secret"], payload)["signature"]
    sig2 = sign_payload.sign_payload(keys["admin2"]["secret"], payload)["signature"]
    admin_body = (
        f'OracleFeed!("admin", "setPaused", true, {admin_nonce}, '
        f'["{sig1}".hexToBytes(), "{sig2}".hexToBytes()], *r) |\n'
        "  for (@x <- r) {\n"
        "    match x {\n"
        '      (true, Nil) => deployId!("ok")\n'
        "      (false, why) => deployId!(why)\n"
        "    }\n"
        "  }"
    )
    check("feed pause", one(call(uri, "OracleFeed", admin_body), secret), "ok")
    paused = one(call(uri, "OracleFeed",
                      'OracleFeed!("get", *r) | for (@x <- r) { deployId!(x) }'), secret)[1]
    check("feed paused reason", paused.get("reason"), "paused")

    print("unit_feed: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
