#!/usr/bin/env python3
"""Exercise OracleRegistry + OracleHub with two live feeds.

Deploys and binds AAA and BBB feeds, then checks routing, pair rate and the
missing-feed refusal through OracleHub.

Usage:
    python3 harness/unit_hub.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import netconfig  # noqa: E402

import deploy as node  # noqa: E402
import sign_payload  # noqa: E402
from install_v3 import render  # noqa: E402
from unit_feed import blake2b256, canonical, deploy_feed  # noqa: E402
from unit_v3 import call, check, one  # noqa: E402

KEYS = netconfig.KEYS_PATH
STATE = netconfig.STATE_PATH
# One policy source. A feed's policy is immutable, so a suite that binds REV
# with a different maxAge makes the later mesh install adopt a policy the
# product did not configure. Load the product policy here instead.
FEED_DEFAULTS = json.loads((ROOT / "configs" / "mesh.json").read_text())["feedDefaults"]
POLICY_FIELDS = ("quorum", "maxAgeBlocks", "maxSpreadBps", "minPrice",
                 "maxPrice", "trialBlocks", "trialMinSubmits")


def setup_feed(keys: dict, root: str, registry: str, currency: str, prices: list[int]):
    sponsor = keys["sponsor"]["public"]
    reporters = [keys[n]["public"] for n in ("reporter1", "reporter2", "reporter3")]
    feed_id = f"{currency}-hub-test-1"
    policy_values = [
        currency, reporters[0], reporters[1], reporters[2], sponsor,
        *(str(FEED_DEFAULTS[field]) for field in POLICY_FIELDS),
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
        "__QUORUM__": str(FEED_DEFAULTS["quorum"]),
        "__MAX_AGE__": str(FEED_DEFAULTS["maxAgeBlocks"]),
        "__MAX_SPREAD__": str(FEED_DEFAULTS["maxSpreadBps"]),
        "__MIN_PRICE__": str(FEED_DEFAULTS["minPrice"]),
        "__MAX_PRICE__": str(FEED_DEFAULTS["maxPrice"]),
        "__TRIAL_BLOCKS__": str(FEED_DEFAULTS["trialBlocks"]),
        "__TRIAL_MIN_SUBMITS__": str(FEED_DEFAULTS["trialMinSubmits"]),
    })
    feed = deploy_feed(term, keys["deployer"]["secret"])
    uri, att_reply = feed
    attest = att_reply[1]
    check(f"{currency} feed attestation", attest.get("feedId"), feed_id)

    height = node.height()
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
        check(f"{currency} submit {index}",
              one(call(uri, "OracleFeed", body), keys["deployer"]["secret"]), "ok")

    activation = one(call(
        uri, "OracleFeed",
        'OracleFeed!("activate", *r) |\n'
        "  for (@x <- r) {\n"
        "    match x {\n"
        '      (true, Nil) => deployId!("ok")\n'
        "      (false, why) => deployId!(why)\n"
        "    }\n"
        "  }"), keys["deployer"]["secret"])
    check(f"{currency} activate", activation, "ok")

    bind_payload = (
        f"rcash:feed-bind:v3|{currency}|{feed_id}|{uri}|{policy_hash}|{sponsor}"
    )
    bind_sig = sign_payload.sign_payload(keys["sponsor"]["secret"],
                                         bind_payload.encode())["signature"]
    bind_term = (
        "new rl(`rho:registry:lookup`), ch, r, "
        "deployerId(`rho:rchain:deployerId`), deployId(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{registry}`, *ch) |\n"
        "  for (Registry <- ch) {\n"
        f'    Registry!("registerFeed", "{currency}", "{uri}", "{feed_id}", '
        f'"{policy_hash}", "{sponsor}", "{bind_sig}".hexToBytes(), *deployerId, *r) |\n'
        "    for (@x <- r) {\n"
        "      match x {\n"
        '        (true, Nil) => deployId!("ok")\n'
        "        (false, why) => deployId!(why)\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}"
    )
    check(f"{currency} bind",
          one(bind_term, keys["sponsor"]["secret"]), "ok")
    return uri, feed_id


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    registry = state["oracle_registry_uri"]
    hub = state["oracle_hub_uri"]

    aaa = setup_feed(keys, root, registry, "AAA", [100, 101, 99])
    bbb = setup_feed(keys, root, registry, "BBB", [1, 1, 1])
    print(f"AAA feed: {aaa}")
    print(f"BBB feed: {bbb}")

    reading = one(call(hub, "OracleHub",
                       'OracleHub!("get", "AAA", *r) | '
                       "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])[1]
    check("hub get fresh", reading.get("fresh"), True)
    check("hub get price", reading.get("price"), 100)

    status = one(call(hub, "OracleHub",
                      'OracleHub!("feedStatus", "AAA", *r) | '
                      "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])[1]
    check("hub status active", status.get("active"), True)

    pair = one(call(hub, "OracleHub",
                    'OracleHub!("getPair", "AAA", "BBB", 50, *r) | '
                    "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])[1]
    check("hub pair fresh", pair.get("fresh"), True)
    check("hub pair rate", pair.get("rate"), 100 * 100000000)

    missing = one(call(hub, "OracleHub",
                       'OracleHub!("getPair", "AAA", "ZZZ", 50, *r) | '
                       "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    check("hub missing feed", missing, (False, "no feed"))

    print("unit_hub: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
