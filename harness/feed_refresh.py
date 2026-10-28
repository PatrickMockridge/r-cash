"""Refresh a bound oracle feed through its three reporters.

Feeds go stale after maxAge blocks, so issuer tests that span several deploys
must re-submit a price before each phase. The feed id and reporter set match the
one `unit_hub.setup_feed` binds.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import deploy as node  # noqa: E402
import sign_payload  # noqa: E402
from unit_hub import setup_feed  # noqa: E402
from unit_v3 import call, check, one  # noqa: E402


def feed_uri(keys: dict, root: str, registry: str, currency: str,
             prices: list[int]) -> tuple[str, str]:
    """Return (uri, feedId) for the bound feed, binding one when absent.

    The feed id is state, not a convention: another installer may have bound
    the code (the mesh binds `REV-mesh-1`). A signature over a guessed id is
    refused by the feed contract, so read the id back from the registry.
    """
    entry = one(call(registry, "OracleRegistry",
                     f'OracleRegistry!("feedEntry", "{currency}", *r) | '
                     "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    if entry[0] is False:
        return setup_feed(keys, root, registry, currency, prices)
    return entry[1]["uri"], entry[1]["feedId"]


def submit_price(keys: dict, feed_ref: tuple[str, str], currency: str,
                 index: int, price: int) -> str:
    feed, feed_id = feed_ref
    height = node.height()
    reporter = keys[f"reporter{index + 1}"]
    payload = f"rcash:oracle-submit:v3|{feed_id}|{currency}|{index}|{price}|{height}"
    sig = sign_payload.sign_payload(reporter["secret"], payload.encode())["signature"]
    body = (
        f'OracleFeed!("submit", {index}, {price}, {height}, "{reporter["public"]}", '
        f'"{sig}".hexToBytes(), *r) |\n'
        "  for (@x <- r) {\n"
        "    match x {\n"
        '      (true, Nil) => deployId!("ok")\n'
        "      (false, why) => deployId!(why)\n"
        "    }\n"
        "  }"
    )
    return one(call(feed, "OracleFeed", body), keys["deployer"]["secret"])


def set_price(keys: dict, feed_ref: tuple[str, str], currency: str, price: int) -> None:
    for index in range(3):
        check(f"{currency} submit {index}",
              submit_price(keys, feed_ref, currency, index, price), "ok")
