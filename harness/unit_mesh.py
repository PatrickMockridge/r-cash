#!/usr/bin/env python3
"""Exercise the unordered-pair mesh and the pauseAsset kill switch.

Requires the mesh installed by `make mesh-install`: the suite derives an active
pair from the on-chain market index instead of assuming one. It then checks
that the reverse orientation resolves to the same market, that staging the
reverse orientation is refused because the pair is active, and that
`pauseAsset(code)` pauses every active market containing the code and nothing
else. Every affected market is resumed, so later suites see the same state.

The reverse staging deliberately uses a *higher* version than the active
market: the pair-active guard is ordered before the version guard, and a
refusal of "pair active" therefore proves the pair guard fired rather than the
version guard.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import deploy as node  # noqa: E402
import sign_payload  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_v3 import call, check, one  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"
MESH_STATE = ROOT / ".devnet" / "mesh-state.json"
TERM_KEYS = [
    "marketId", "slug", "base", "quote", "version", "sponsorPubKey",
    "sponsorOwnerId", "baseFeedPolicyHash", "quoteFeedPolicyHash",
    "baseSpreadBps", "skewSpreadBps", "maxTradeBps", "minLiquidity",
    "firstDepositToleranceBps", "depthFloorQuote", "minTicketQuote",
    "seedBase", "seedQuote", "seedInitialShares", "lockBeneficiaryPubKey",
    "lockMinBlocks", "lockUntilHeight", "bookDefaultExpiryBlocks",
    "bookMaxExpiryBlocks", "maxPairAgeBlocks",
]


def canonical(schema: str, values: list[str]) -> str:
    return schema + "|" + "|".join(f"{len(v)}:{v}" for v in values)


def admin_sigs(keys: dict, domain: str, nonce: int, action: str, args: str) -> str:
    payload = f"rcash:admin:v1|{domain}|{nonce}|{action}|{args}"
    return ", ".join(
        f'"{sign_payload.sign_payload(keys[name]["secret"], payload.encode())["signature"]}".hexToBytes()'
        for name in ("admin1", "admin2"))


def market_for(state: dict, secret: str, base: str, quote: str) -> tuple:
    return one(call(state["market_index_uri"], "MarketIndex",
                    f'MarketIndex!("marketFor", "{base}", "{quote}", *r) | '
                    "for (@x <- r) { deployId!(x) }"), secret)


def markets(state: dict, secret: str) -> dict:
    reply = one(call(state["market_index_uri"], "MarketIndex",
                     'MarketIndex!("markets", *r) | '
                     "for (@x <- r) { deployId!(x) }"), secret)
    check("markets readable", reply[0], True)
    return reply[1]


def market(state: dict, secret: str, market_id: str) -> tuple:
    return one(call(state["market_index_uri"], "MarketIndex",
                    f'MarketIndex!("market", "{market_id}", *r) | '
                    "for (@x <- r) { deployId!(x) }"), secret)


def active_pair(keys: dict, state: dict) -> tuple[str, str]:
    if not MESH_STATE.is_file():
        raise AssertionError("mesh not installed; run make mesh-install first")
    pairs = json.loads(MESH_STATE.read_text()).get("pairs") or []
    active = [p for p in pairs if p.get("status") == "active"]
    if not active:
        raise AssertionError("mesh state has no active pair")
    chosen = next((p for p in active
                   if p.get("base") == "NGN" and p.get("quote") == "USD"), active[0])
    return chosen["base"], chosen["quote"]


def set_status(state: dict, keys: dict, secret: str, market_id: str,
               status: str, nonce: int) -> tuple:
    args = f"{market_id}|{status}"
    sigs = admin_sigs(keys, "market-index", nonce, "setStatus", args)
    return one(call(state["market_index_uri"], "MarketIndex",
                    f'MarketIndex!("setStatus", "{market_id}", "{status}", '
                    f"{nonce}, [{sigs}], *r) | "
                    "for (@x <- r) { deployId!(x) }"), secret)


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    secret = keys["deployer"]["secret"]
    base, quote = active_pair(keys, state)

    forward = market_for(state, secret, base, quote)
    if forward[0] is not True:
        raise AssertionError(f"{base}/{quote} active pair missing from the index")
    check("forward market active", forward[1].get("status"), "active")
    check("forward market orientation", (forward[1].get("base"), forward[1].get("quote")),
          (base, quote))
    reverse = market_for(state, secret, quote, base)
    check("reverse lookup resolves", reverse[0], True)
    check("reverse lookup same market", reverse[1].get("marketId"),
          forward[1].get("marketId"))

    # Stage the same unordered pair in the reverse orientation with a higher
    # version. The active pair owns the pair key, so the refusal must be the
    # pair guard, not the version guard.
    terms_hash = forward[1].get("termsHash")
    entry = one(call(state["market_terms_uri"], "MarketTerms",
                     f'MarketTerms!("get", "{terms_hash}", *r) | '
                     "for (@x <- r) { deployId!(x) }"), secret)
    if entry[0] is not True:
        raise AssertionError(f"terms missing: {entry}")
    values = list(entry[1]["values"])
    terms = dict(entry[1]["terms"])
    new_version = int(values[4]) + 1
    new_values = list(values)
    new_values[0] = f"{quote}/{base}:v{new_version}"
    new_values[1] = f"{quote.lower()}-{base.lower()}-v{new_version}"
    new_values[2], new_values[3] = quote, base
    new_values[4] = str(new_version)
    new_values[7], new_values[8] = values[8], values[7]
    new_terms = dict(terms)
    new_terms["marketId"] = new_values[0]
    new_terms["slug"] = new_values[1]
    new_terms["base"], new_terms["quote"] = quote, base
    new_terms["version"] = new_version
    new_terms["baseFeedPolicyHash"], new_terms["quoteFeedPolicyHash"] = values[8], values[7]
    new_hash = canonical("rcash:market-terms:v4", new_values)
    sponsor = terms["sponsorPubKey"]
    sponsor_key = next(name for name in ("sponsor", "deployer")
                       if keys[name]["public"] == sponsor)
    payload = f"rcash:market-create:v1|{new_values[0]}|{new_hash}|{sponsor}"
    sig = sign_payload.sign_payload(keys[sponsor_key]["secret"], payload.encode())["signature"]
    terms_literal = "{" + ", ".join(
        f'"{key}": {json.dumps(new_terms[key])}' for key in TERM_KEYS) + "}"
    values_literal = "[" + ", ".join(json.dumps(v) for v in new_values) + "]"
    body = (
        "new rl(`rho:registry:lookup`), ch, r, deployId(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{state['market_factory_uri']}`, *ch) |\n"
        "  for (MarketFactory <- ch) {\n"
        f"    MarketFactory!(\"createMarket\", {terms_literal}, {values_literal}, "
        f"\"{sponsor}\", \"{sig}\".hexToBytes(), *r) |\n"
        "    for (@x <- r) { deployId!(x) }\n"
        "  }\n"
        "}"
    )
    refused = one(minify(body), secret)
    check("reverse staging refused", refused[0], False)
    check("reverse staging reason", refused[1], "pair active")
    absent = market(state, secret, new_values[0])
    check("reverse staging created no market", absent, (False, "no market"))

    # pauseAsset(code) is a state transition over every active market that
    # contains the code; all other records must be unchanged.
    before = markets(state, secret)
    affected = sorted(
        market_id for market_id, record in before.items()
        if base in (record.get("base"), record.get("quote"))
        and record.get("status") == "active"
    )
    check(f"pauseAsset affects more than one {base} market", len(affected) >= 2, True)
    nonce = node.height()
    sigs = admin_sigs(keys, "market-index", nonce, "pauseAsset", base)
    pause = one(call(state["market_index_uri"], "MarketIndex",
                     f'MarketIndex!("pauseAsset", "{base}", {nonce}, [{sigs}], *r) | '
                     "for (@x <- r) { deployId!(x) }"), secret)
    check("pauseAsset accepted", pause[0], True)
    after = markets(state, secret)
    for market_id in affected:
        check(f"{market_id} paused by asset", after[market_id].get("status"), "paused")
    for market_id, record in before.items():
        if market_id not in affected:
            check(f"{market_id} unchanged", after[market_id], record)

    # Resume every paused market so later suites see the same state as before.
    resume_nonce = nonce
    for market_id in affected:
        resume_nonce += 1
        check(f"{market_id} resume accepted",
              set_status(state, keys, secret, market_id, "active", resume_nonce)[0], True)
        check(f"{market_id} active again",
              market(state, secret, market_id)[1].get("status"), "active")
    restored = markets(state, secret)
    for market_id in affected:
        check(f"{market_id} restored", restored[market_id].get("status"), "active")
    print("unit_mesh: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
