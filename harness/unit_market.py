#!/usr/bin/env python3
"""Exercise the v0.4 direct market: create, seed, activate, swap.

Creates the REV/V4T market from sponsor-signed terms, seeds it from the
provider's account (REV plus V4T minted against a vault), activates it, and
swaps REV for V4T through the pool.

Run after `make unit-stablecoin`: the market needs a listed V4T system and
fresh REV/V4T feeds.

Usage:
    python3 harness/unit_market.py
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
from feed_refresh import feed_uri, set_price  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_feed import canonical  # noqa: E402
from unit_v3 import call, check, faucet_top_up, one  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"
SCENARIOS = ROOT / "harness" / "scenarios"
MARKET_ID = "REV/V4T:v1"
BASE = "REV"
QUOTE = "V4T"
SPREAD = 30
SKEW = 10
FUND_REV = 800_000_000
COLLATERAL = 500_000_000
MINT = 15_000_000_000
BASE_AMT = 200_000_000
QUOTE_AMT = 15_000_000_000
FUND_SWAP = 10_000_000
SWAP_AMT = 5_000_000


def render_scenario(name: str, values: dict) -> str:
    text = (SCENARIOS / name).read_text()
    for key, value in values.items():
        text = text.replace(key, value)
    return minify(text)


def rholang_value(value) -> str:
    if isinstance(value, int):
        return str(value)
    return f'"{value}"'


def wait_height(target: int) -> None:
    import time
    for _ in range(60):
        if node.height() > target:
            return
        time.sleep(2)
    raise AssertionError(f"height did not pass {target}")


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    registry = state["oracle_registry_uri"]
    currency_registry = state["currency_registry_uri"]
    factory = state["market_factory_uri"]
    index = state["market_index_uri"]
    sponsor = keys["sponsor"]
    faucet_top_up(keys["key18"]["address"])
    lock_until = node.height() + 20

    listed = one(call(currency_registry, "CurrencyRegistry",
                      'CurrencyRegistry!("currency", "V4T", *r) | '
                      "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    if not listed[0]:
        raise AssertionError("V4T is not listed; run make unit-stablecoin first")

    rev_feed = feed_uri(keys, root, registry, "REV", [5_000_000] * 3)
    v4t_feed = feed_uri(keys, root, registry, "V4T", [66_666] * 3)
    set_price(keys, v4t_feed, "V4T", 66_666)
    set_price(keys, rev_feed, "REV", 5_000_000)

    def entry(feed: str, code: str) -> dict:
        return one(call(registry, "OracleRegistry",
                        f'OracleRegistry!("feedEntry", "{code}", *r) | '
                        "for (@x <- r) { deployId!(x) }"),
                   keys["deployer"]["secret"])[1]

    rev_entry = entry(rev_feed, "REV")
    v4t_entry = entry(v4t_feed, "V4T")

    fields = [
        ("marketId", MARKET_ID), ("slug", "rev-v4t"), ("base", BASE), ("quote", QUOTE),
        ("version", 1), ("sponsorPubKey", sponsor["public"]),
        ("sponsorOwnerId", sponsor["address"]),
        ("baseFeedPolicyHash", rev_entry.get("policyHash")),
        ("quoteFeedPolicyHash", v4t_entry.get("policyHash")),
        ("baseSpreadBps", SPREAD), ("skewSpreadBps", SKEW), ("maxTradeBps", 2000),
        ("minLiquidity", 1_000_000), ("firstDepositToleranceBps", 1000),
        ("depthFloorQuote", 100_000_000), ("minTicketQuote", 1_000_000),
        ("seedBase", BASE_AMT), ("seedQuote", QUOTE_AMT),
        ("seedInitialShares", 1_000_000_000),
        ("lockBeneficiaryPubKey", sponsor["public"]),
        ("lockMinBlocks", 10), ("lockUntilHeight", lock_until),
        ("bookDefaultExpiryBlocks", 100), ("bookMaxExpiryBlocks", 1000),
        ("maxPairAgeBlocks", 50),
    ]
    values = [str(v) for _, v in fields]
    terms_hash = canonical("rcash:market-terms:v4", values)
    terms_literal = "{" + ", ".join(
        f'"{key}": {rholang_value(value)}' for key, value in fields) + "}"
    values_literal = "[" + ", ".join(f'"{v}"' for v in values) + "]"
    payload = f"rcash:market-create:v1|{MARKET_ID}|{terms_hash}|{sponsor['public']}"
    sig = sign_payload.sign_payload(sponsor["secret"], payload.encode())["signature"]

    create_term = (
        "new rl(`rho:registry:lookup`), ch, r, deployId(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{factory}`, *ch) |\n"
        "  for (MarketFactory <- ch) {\n"
        f'    MarketFactory!("createMarket", {terms_literal}, {values_literal}, '
        f'"{sponsor["public"]}", "{sig}".hexToBytes(), *r) |\n'
        "    for (@x <- r) {\n"
        "      match x {\n"
        '        (true, mid, poolUri, lockUri, hash) => deployId!([mid, poolUri, lockUri, hash])\n'
        "        _ => deployId!(x)\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}"
    )
    created = one(create_term, keys["deployer"]["secret"])
    if created[0] is True:
        check("market created", created[0], MARKET_ID)
        pool_uri, lock_uri = created[1], created[2]
        check("market terms hash", created[3], terms_hash)
    else:
        # A previous run on this chain already created and sealed the market.
        directory = state["market_directory_uri"]
        slot = one(call(directory, "MarketDirectory",
                        f'MarketDirectory!("byId", "{MARKET_ID}", *r) | '
                        "for (@x <- r) { deployId!(x) }"),
                   keys["deployer"]["secret"])
        if not slot[0]:
            raise AssertionError(f"market create refused: {created}")
        pool_uri, lock_uri = slot[1].get("poolUri"), slot[1].get("lockUri")
        print("market already created; reusing the sealed slot")
    print(f"pool: {pool_uri}")
    print(f"lock: {lock_uri}")

    set_price(keys, v4t_feed, "V4T", 66_666)
    set_price(keys, rev_feed, "REV", 5_000_000)

    def reserves() -> dict:
        return one(call(pool_uri, "FxPool",
                        'FxPool!("reserves", *r) | for (@x <- r) { deployId!(x) }'),
                   keys["deployer"]["secret"])[1]

    rate = 5_000_000 * 100_000_000 // 66_666
    before = reserves()
    if before.get("seeded"):
        print("pool already seeded; skipping the seed")
        shares = None
    else:
        seed_term = render_scenario("market_seed.rho", {
        "__ROOT_URI__": root,
        "__REGISTRY_URI__": currency_registry,
        "__POOL_URI__": pool_uri,
        "__LOCK_URI__": lock_uri,
        "__LOCK_UNTIL__": str(lock_until),
        "__PUBKEY__": keys["deployer"]["public"],
        "__FUND_REV__": str(FUND_REV),
        "__COLLATERAL__": str(COLLATERAL),
        "__MINT__": str(MINT),
        "__BASE_AMT__": str(BASE_AMT),
        "__QUOTE_AMT__": str(QUOTE_AMT),
    })
        seeded = one(seed_term, keys["deployer"]["secret"])
        if isinstance(seeded[2], dict):
            shares, seeded_reserves, lock_shares = seeded[1], seeded[2], seeded[3]
        else:
            shares, seeded_reserves, lock_shares = seeded[1], seeded[2][1], seeded[3]
        check("seed locked", lock_shares, shares)
        deposit_value = (BASE_AMT * rate) // 100_000_000 + QUOTE_AMT
        check("initial shares", shares, deposit_value - 100_000_000)
        check("base reserve", seeded_reserves.get("base"), BASE_AMT)
        check("quote reserve", seeded_reserves.get("quote"), QUOTE_AMT)

    activation = one(call(index, "MarketIndex",
                          f'MarketIndex!("activate", "{MARKET_ID}", *r) | '
                          "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    if activation != (True, "active"):
        check("market already active", activation, (False, "not draft"))
    record = one(call(index, "MarketIndex",
                      f'MarketIndex!("marketFor", "{BASE}", "{QUOTE}", *r) | '
                      "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])[1]
    check("marketFor status", record.get("status"), "active")
    if created[0] is True:
        check("marketFor pool", record.get("termsHash"), terms_hash)
    else:
        check("marketFor pool", isinstance(record.get("termsHash"), str), True)

    set_price(keys, v4t_feed, "V4T", 66_666)
    set_price(keys, rev_feed, "REV", 5_000_000)
    swap_term = render_scenario("market_swap.rho", {
        "__ROOT_URI__": root,
        "__POOL_URI__": pool_uri,
        "__PUBKEY__": keys["key18"]["public"],
        "__FUND__": str(FUND_SWAP),
        "__AMOUNT__": str(SWAP_AMT),
    })
    pre = reserves()
    base_value = (pre["base"] * rate) // 100_000_000
    pool_value = base_value + pre["quote"]
    weight = (base_value * 10000) // pool_value if pool_value > 0 else 5000
    fee = SPREAD + (abs(weight - 5000) * SKEW) // 5000
    gross = (SWAP_AMT * rate) // 100_000_000
    expected_out = (gross * (10000 - fee)) // 10000

    out, balance = one(swap_term, keys["key18"]["secret"])
    check("swap output", out, expected_out)
    check("swap credited", balance, (True, expected_out))

    after = reserves()
    check("base reserve after swap", after.get("base"), pre["base"] + SWAP_AMT)
    check("quote reserve after swap", after.get("quote"), pre["quote"] - expected_out)

    wait_height(lock_until)
    release_term = render_scenario("market_release.rho", {
        "__ROOT_URI__": root,
        "__LOCK_URI__": lock_uri,
        "__POOL_URI__": pool_uri,
    })
    released = one(release_term, keys["deployer"]["secret"])
    released_shares, final = released[0], released[1][1]
    check("release returned the seed", released_shares > 0, True)
    check("liquidity removed", final.get("totalShares"), 0)
    check("base reserve cleared", final.get("base"), 0)
    check("quote reserve cleared", final.get("quote"), 0)
    closed_term = (
        "new rl(`rho:registry:lookup`), ch, r, "
        "deployId(`rho:rchain:deployId`), deployerId(`rho:rchain:deployerId`) in {\n"
        f"  rl!(`{lock_uri}`, *ch) |\n"
        "  for (LiquidityLock <- ch) {\n"
        '    LiquidityLock!("release", *deployerId, *r) |\n'
        "    for (@x <- r) { deployId!(x) }\n"
        "  }\n"
        "}"
    )
    check("second release refused",
          one(closed_term, keys["deployer"]["secret"]), (False, "closed"))

    # --- listing views, tradability gate, pause/delist and a second version ---
    views = state["listing_views_uri"]
    gate = state["tradability_gate_uri"]
    check("view isActive",
          one(call(views, "ListingViews",
                   'ListingViews!("isActive", "REV/V4T:v1", *r) | '
                   "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"]),
          (True, True))
    view_record = one(call(views, "ListingViews",
                           'ListingViews!("marketFor", "REV", "V4T", *r) | '
                           "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])[1]
    check("view market status", view_record.get("status"), "active")
    terms_view = one(call(views, "ListingViews",
                          f'ListingViews!("terms", "{terms_hash}", *r) | '
                          "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])[1]
    check("view terms base", terms_view.get("terms").get("base"), "REV")
    currency_view = one(call(views, "ListingViews",
                             'ListingViews!("currency", "V4T", *r) | '
                             "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])[1]
    check("view currency", currency_view.get("status"), "active")

    gate_terms = '{"minTicketQuote": 1000000, "maxTradeBps": 2000}'
    def admit(status: str, fresh: bool, value: int, pool: int) -> list:
        body = (f'TradabilityGate!("admit", "{status}", {str(fresh).lower()}, '
                f"{value}, {pool}, {gate_terms}, *r) | "
                "for (@x <- r) { deployId!(x) }")
        return one(call(gate, "TradabilityGate", body), keys["deployer"]["secret"])

    check("gate admits", admit("active", True, 1_000_000_000, 30_000_000_000)[0], True)
    check("gate refuses inactive", admit("paused", True, 1_000_000_000, 30_000_000_000),
          (False, "not active"))
    check("gate refuses stale", admit("active", False, 1_000_000_000, 30_000_000_000),
          (False, "stale"))
    check("gate refuses min ticket", admit("active", True, 100, 30_000_000_000),
          (False, "min ticket"))
    check("gate refuses max trade", admit("active", True, 10_000_000_000, 30_000_000_000),
          (False, "max trade"))

    def set_status(status: str, nonce: int) -> list:
        args = f"REV/V4T:v1|{status}"
        payload = f"rcash:admin:v1|market-index|{nonce}|setStatus|{args}"
        sigs = ", ".join(
            f'"{sign_payload.sign_payload(keys[n]["secret"], payload.encode())["signature"]}".hexToBytes()'
            for n in ("admin1", "admin2"))
        body = (f'MarketIndex!("setStatus", "REV/V4T:v1", "{status}", {nonce}, '
                f"[{sigs}], *r) | for (@x <- r) {{ deployId!(x) }}")
        return one(call(index, "MarketIndex", body), keys["deployer"]["secret"])

    status_nonce = node.height()
    check("market paused", set_status("paused", status_nonce), (True, "paused"))
    check("paused view", one(call(views, "ListingViews",
                                  'ListingViews!("isActive", "REV/V4T:v1", *r) | '
                                  "for (@x <- r) { deployId!(x) }"),
                             keys["deployer"]["secret"]), (True, False))
    paused_quote = one(call(pool_uri, "FxPool",
                            'FxPool!("quote", "b2q", 1000000, *r) | '
                            "for (@x <- r) { deployId!(x) }"),
                       keys["deployer"]["secret"])
    check("quote refuses a paused market", paused_quote, (False, "not active"))
    check("market resumed", set_status("active", status_nonce + 1), (True, "active"))
    check("market delisted", set_status("delisted", status_nonce + 2), (True, "delisted"))

    fields2 = [(key, "REV/V4T:v2" if key == "marketId"
                else 2 if key == "version" else value) for key, value in fields]
    values2 = [str(v) for _, v in fields2]
    hash2 = canonical("rcash:market-terms:v4", values2)
    literal2 = "{" + ", ".join(
        f'"{key}": {rholang_value(value)}' for key, value in fields2) + "}"
    values2_literal = "[" + ", ".join(f'"{v}"' for v in values2) + "]"
    payload2 = f"rcash:market-create:v1|REV/V4T:v2|{hash2}|{sponsor['public']}"
    sig2 = sign_payload.sign_payload(sponsor["secret"], payload2.encode())["signature"]
    create2 = (
        "new rl(`rho:registry:lookup`), ch, r, deployId(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{factory}`, *ch) |\n"
        "  for (MarketFactory <- ch) {\n"
        f'    MarketFactory!("createMarket", {literal2}, {values2_literal}, '
        f'"{sponsor["public"]}", "{sig2}".hexToBytes(), *r) |\n'
        "    for (@x <- r) {\n"
        "      match x {\n"
        '        (true, mid, poolUri, lockUri, hash) => deployId!([mid, poolUri, lockUri, hash])\n'
        "        _ => deployId!(x)\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}"
    )
    created2 = one(create2, keys["deployer"]["secret"])
    check("version 2 staged", created2[0], "REV/V4T:v2")
    v2_record = one(call(index, "MarketIndex",
                         'MarketIndex!("market", "REV/V4T:v2", *r) | '
                         "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])[1]
    check("version 2 draft", v2_record.get("status"), "draft")
    check("version 2 version", v2_record.get("version"), 2)

    print(json.dumps({"market": MARKET_ID, "pool": pool_uri,
                      "termsHash": terms_hash, "shares": shares,
                      "swapOut": out, "reserves": after}, indent=2))
    print("unit_market: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
