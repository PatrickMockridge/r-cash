"""Shared provisioning for the currency mesh.

The functions use the same deploy path as the unit harnesses: signed params,
one deploy per component, and signed reads for the replies. They are used by
`tools/mesh.py`; they are not a second protocol implementation.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import netconfig  # noqa: E402

import deploy as node  # noqa: E402
import sign_payload  # noqa: E402
from install_v3 import render  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_feed import blake2b256, canonical, deploy_feed  # noqa: E402
from unit_stablecoin import deploy_system  # noqa: E402
from unit_v3 import call, check, faucet_top_up, one  # noqa: E402

STATE = netconfig.STATE_PATH
KEYS = netconfig.KEYS_PATH


def load_env() -> tuple[dict, dict]:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    if "currency_registry_uri" not in state:
        steps = state.get("steps", {})
        state["currency_registry_uri"] = steps["currency_registry"]["uris"][1]
        state["stablecoin_directory_uri"] = steps["currency_registry"]["uris"][0]
    return keys, state


def issuer_values(config: dict, currency: str) -> tuple[dict, list[str], str]:
    p = config["issuerDefaults"]
    values = [
        currency,
        str(p["mcrBps"]), str(p["bonusBps"]), str(p["closeFactorBps"]),
        str(p["ratePerBlock"]), str(p["debtCeiling"]), str(p["minDebt"]),
        str(p["maxDebt"]), str(p["maxOracleAge"]), str(p["savingsShareBps"]),
        str(p["psmFeeBps"]),
    ]
    params = {
        "mcrBps": p["mcrBps"], "bonusBps": p["bonusBps"],
        "closeFactorBps": p["closeFactorBps"], "ratePerBlock": p["ratePerBlock"],
        "debtCeiling": p["debtCeiling"], "minDebt": p["minDebt"],
        "maxDebt": p["maxDebt"], "maxOracleAge": p["maxOracleAge"],
        "savingsShareBps": p["savingsShareBps"], "psmFeeBps": p["psmFeeBps"],
    }
    params_hash = blake2b256(canonical("rcash:stablecoin-params:v2", values))
    return params, values, params_hash


def existing_currency(keys: dict, state: dict, code: str) -> dict | None:
    reply = one(call(state["currency_registry_uri"], "CurrencyRegistry",
                     f'CurrencyRegistry!("currency", "{code}", *r) | '
                     "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    return reply[1] if reply and reply[0] is True else None


def _submit_price(keys: dict, feed: str, feed_id: str, code: str, price: int) -> None:
    height = node.height()
    for index in range(3):
        reporter = keys[config_reporter(index)]
        payload = f"rcash:oracle-submit:v3|{feed_id}|{code}|{index}|{price}|{height}"
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
        reply = one(call(feed, "OracleFeed", body), keys["deployer"]["secret"])
        if reply != "ok":
            raise RuntimeError(f"{code} submit {index} failed: {reply}")


def config_reporter(index: int) -> str:
    return f"reporter{index + 1}"


FEED_POLICY_FIELDS = ("quorum", "maxAgeBlocks", "maxSpreadBps", "minPrice",
                      "maxPrice", "trialBlocks", "trialMinSubmits")


def check_feed_policy(keys: dict, feed: str, code: str, policy: dict) -> None:
    """Refuse to adopt a bound feed whose policy is not the mesh policy.

    A feed's policy is fixed at deployment; the registry allows one feed per
    code. Reusing a feed bound by another suite therefore adopts that suite's
    `maxAgeBlocks` as if it were the product's. That state is not
    representable: mismatch is an installation error, not something to refresh
    around.
    """
    info = one(call(feed, "OracleFeed",
                    'OracleFeed!("info", *r) | '
                    "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    if not info or info[0] is not True:
        raise RuntimeError(f"{code} feed info failed: {info}")
    current = info[1]
    if current.get("currency") != code:
        raise RuntimeError(f"{code} feed serves {current.get('currency')!r}")
    for field in FEED_POLICY_FIELDS:
        if current.get(field) != policy[field]:
            raise RuntimeError(
                f"{code} feed policy mismatch: {field} is {current.get(field)}, "
                f"config requires {policy[field]}; bind a feed with the mesh "
                f"policy on a fresh chain")


def ensure_feed(keys: dict, state: dict, config: dict, code: str, price: int) -> str:
    registry = state["oracle_registry_uri"]
    sponsor = keys[config["sponsorKey"]]
    reporters = [keys[name]["public"] for name in config["reporters"]]
    feed_id = f"{code}-mesh-1"
    policy = config["feedDefaults"]
    entry = one(call(registry, "OracleRegistry",
                     f'OracleRegistry!("feedEntry", "{code}", *r) | '
                     "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    if entry and entry[0] is True:
        feed = entry[1]["uri"]
        check_feed_policy(keys, feed, code, policy)
        _submit_price(keys, feed, entry[1].get("feedId", feed_id), code, price)
        return feed
    values = [
        code, reporters[0], reporters[1], reporters[2], sponsor["public"],
        str(policy["quorum"]), str(policy["maxAgeBlocks"]),
        str(policy["maxSpreadBps"]), str(policy["minPrice"]),
        str(policy["maxPrice"]), str(policy["trialBlocks"]),
        str(policy["trialMinSubmits"]),
    ]
    policy_hash = blake2b256(canonical("rcash:oracle-policy:v3", values))
    term = render("31_feed", {
        "__ROOT_URI__": state["root_uri"],
        "__CURRENCY__": code,
        "__FEED_ID__": feed_id,
        "__REPORTERS__": "[" + ", ".join(f'"{key}"' for key in reporters) + "]",
        "__SPONSOR_PUB__": sponsor["public"],
        "__POLICY_HASH__": policy_hash,
        "__QUORUM__": str(policy["quorum"]),
        "__MAX_AGE__": str(policy["maxAgeBlocks"]),
        "__MAX_SPREAD__": str(policy["maxSpreadBps"]),
        "__MIN_PRICE__": str(policy["minPrice"]),
        "__MAX_PRICE__": str(policy["maxPrice"]),
        "__TRIAL_BLOCKS__": str(policy["trialBlocks"]),
        "__TRIAL_MIN_SUBMITS__": str(policy["trialMinSubmits"]),
    })
    feed = deploy_feed(term, keys["deployer"]["secret"])[0]
    _submit_price(keys, feed, feed_id, code, price)
    activate = one(call(feed, "OracleFeed",
                        'OracleFeed!("activate", *r) |\n'
                        "  for (@x <- r) {\n"
                        "    match x {\n"
                        '      (true, Nil) => deployId!("ok")\n'
                        "      (false, why) => deployId!(why)\n"
                        "    }\n"
                        "  }"), keys["deployer"]["secret"])
    if activate != "ok":
        raise RuntimeError(f"{code} feed activate failed: {activate}")
    bind_payload = (f"rcash:feed-bind:v3|{code}|{feed_id}|{feed}|{policy_hash}|"
                    f"{sponsor['public']}")
    bind_sig = sign_payload.sign_payload(sponsor["secret"], bind_payload.encode())["signature"]
    bind_term = (
        "new rl(`rho:registry:lookup`), ch, r, "
        "deployerId(`rho:rchain:deployerId`), deployId(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{registry}`, *ch) |\n"
        "  for (Registry <- ch) {\n"
        f'    Registry!("registerFeed", "{code}", "{feed}", "{feed_id}", '
        f'"{policy_hash}", "{sponsor["public"]}", "{bind_sig}".hexToBytes(), '
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
    faucet_top_up(sponsor["address"])
    bound = one(bind_term, sponsor["secret"])
    if bound != "ok":
        raise RuntimeError(f"{code} feed bind failed: {bound}")
    return feed


def deploy_and_register_issuer(keys: dict, state: dict, config: dict, currency: str) -> dict:
    existing = existing_currency(keys, state, currency)
    if existing is not None:
        return existing
    sponsor = keys[config["sponsorKey"]]["public"]
    params, _values, params_hash = issuer_values(config, currency)
    payload = f"rcash:stablecoin-create:v1|{currency}|{params_hash}|{sponsor}"
    sig = sign_payload.sign_payload(keys[config["sponsorKey"]]["secret"],
                                    payload.encode())["signature"]
    term = render("31_stablecoin", {
        "__ROOT_URI__": state["root_uri"],
        "__CURRENCY__": currency,
        "__PARAMS__": json.dumps(params),
        "__PARAMS_HASH__": params_hash,
        "__SPONSOR_PUB__": sponsor,
        "__SPONSOR_SIG__": sig,
    })
    system = deploy_system(term, keys["deployer"]["secret"])
    (sc_uri, custody_uri, params_uri, vault_uri, liq_uri, savings_uri,
     psm_uri, buffer_uri, _attest) = system

    listing = (f"rcash:currency-register:v3|{currency}|{sc_uri}|{custody_uri}|"
               f"{params_uri}|{vault_uri}|{liq_uri}|{savings_uri}|{psm_uri}|"
               f"{buffer_uri}|{params_hash}|{sponsor}")
    listing_sig = sign_payload.sign_payload(keys[config["sponsorKey"]]["secret"],
                                            listing.encode())["signature"]
    body = (
        f'CurrencyRegistry!("register", "{currency}", "{sc_uri}", "{custody_uri}", '
        f'"{params_uri}", "{vault_uri}", "{liq_uri}", "{savings_uri}", "{psm_uri}", '
        f'"{buffer_uri}", "{params_hash}", "{sponsor}", '
        f'"{listing_sig}".hexToBytes(), *r) |\n'
        "  for (@x <- r) {\n"
        "    match x {\n"
        '      (true, entry) => deployId!([true, entry])\n'
        "      (false, why) => deployId!([false, why])\n"
        "      _ => deployId!(x)\n"
        "    }\n"
        "  }"
    )
    listed = one(call(state["currency_registry_uri"], "CurrencyRegistry", body),
                 keys["deployer"]["secret"])
    if not listed or listed[0] is not True:
        raise RuntimeError(f"{currency} listing failed: {listed}")
    check(f"{currency} listed", listed[1].get("stablecoinUri"), sc_uri)
    return listed[1]


def register_external(keys: dict, state: dict, config: dict, code: str,
                      adapter_uri: str) -> dict:
    existing = existing_currency(keys, state, code)
    if existing is not None:
        return existing
    sponsor = keys[config["sponsorKey"]]["public"]
    payload = f"rcash:external-asset-register:v1|{code}|{adapter_uri}|{sponsor}"
    sig = sign_payload.sign_payload(keys[config["sponsorKey"]]["secret"],
                                    payload.encode())["signature"]
    body = (
        f'CurrencyRegistry!("registerExternal", "{code}", "{adapter_uri}", '
        f'"{sponsor}", "{sig}".hexToBytes(), *r) |\n'
        "  for (@x <- r) {\n"
        "    match x {\n"
        '      (true, entry) => deployId!([true, entry])\n'
        "      (false, why) => deployId!([false, why])\n"
        "      _ => deployId!(x)\n"
        "    }\n"
        "  }"
    )
    reply = one(call(state["currency_registry_uri"], "CurrencyRegistry", body),
                keys["deployer"]["secret"])
    if not reply or reply[0] is not True:
        raise RuntimeError(f"{code} external listing failed: {reply}")
    return reply[1]


def feed_policy_hash(keys: dict, state: dict, code: str) -> str:
    entry = one(call(state["oracle_registry_uri"], "OracleRegistry",
                     f'OracleRegistry!("feedEntry", "{code}", *r) | '
                     "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    if not entry or entry[0] is not True:
        raise RuntimeError(f"no oracle feed for {code}: {entry}")
    return entry[1].get("policyHash")


def pair_rate(keys: dict, state: dict, base: str, quote: str, max_age: int = 50) -> int:
    reply = one(call(state["oracle_hub_uri"], "OracleHub",
                     f'OracleHub!("getPair", "{base}", "{quote}", {max_age}, *r) | '
                     "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    if not reply or reply[0] is not True:
        raise RuntimeError(f"no rate for {base}/{quote}: {reply}")
    rate = reply[1].get("rate")
    if not isinstance(rate, int) or rate <= 0:
        raise RuntimeError(f"bad rate for {base}/{quote}: {reply}")
    return rate


def feed_price(config: dict, code: str) -> int:
    if code == "REV":
        if config.get("revPriceE8"):
            return int(config["revPriceE8"])
        return max(1, config["currencies"][0]["initialPriceE8"] // 20)
    for currency in config["currencies"]:
        if currency["code"] == code:
            return currency.get("initialPriceE8", 100_000_000)
    raise RuntimeError(f"no configured price for {code}")


def publish_prices(keys: dict, state: dict, config: dict,
                   codes: tuple[str, ...]) -> None:
    """Publish every feed a pair phase will consume, at the start of the phase.

    The oracle's freshness rule is window-based: a consumer is valid only while
    the latest report is within `maxAgeBlocks`. Provisioning a whole mesh takes
    far longer than one window, so a single publish at install start leaves the
    later phases reading a state the protocol already defines as stale. The
    phase therefore publishes first and consumes immediately; there is no
    retry, because a refusal means the phase outlived its window and that is a
    liveness result to report, not a state to paper over.
    """
    for code in dict.fromkeys(codes):
        ensure_feed(keys, state, config, code, feed_price(config, code))


def rholang_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise TypeError(f"unsupported Rholang value: {value!r}")


def market_for(keys: dict, state: dict, base: str, quote: str) -> dict | None:
    reply = one(call(state["market_index_uri"], "MarketIndex",
                     f'MarketIndex!("marketFor", "{base}", "{quote}", *r) | '
                     "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    return reply[1] if reply and reply[0] is True else None


def market_slot(keys: dict, state: dict, market_id: str) -> dict:
    reply = one(call(state["market_directory_uri"], "MarketDirectory",
                     f'MarketDirectory!("slot", "{market_id}", *r) | '
                     "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    if not reply or reply[0] is not True:
        raise RuntimeError(f"no slot for {market_id}: {reply}")
    return reply[1]


def create_market(keys: dict, state: dict, config: dict, base: str, quote: str,
                  sponsor_key: str | None = None) -> dict:
    existing = market_for(keys, state, base, quote)
    if existing is not None:
        return {"market": existing, "slot": market_slot(keys, state, existing["marketId"]),
                "created": False}
    md = config["marketDefaults"]
    sponsor_key = sponsor_key or config["marketSponsorKey"]
    sponsor = keys[sponsor_key]
    publish_prices(keys, state, config, (base, quote))
    rate = pair_rate(keys, state, base, quote, md["maxPairAgeBlocks"])
    seed_quote = max(md["seedQuoteTarget"], md["depthFloorQuote"], md["minTicketQuote"] * 10)
    seed_base = max(1, seed_quote * 100_000_000 // rate)
    height = node.height()
    lock_until = height + md["lockUntilBlocks"]
    market_id = f"{base}/{quote}:v1"
    slug = f"{base.lower()}-{quote.lower()}-v1"
    fields = [
        ("marketId", market_id), ("slug", slug), ("base", base), ("quote", quote),
        ("version", 1), ("sponsorPubKey", sponsor["public"]),
        ("sponsorOwnerId", sponsor["address"]),
        ("baseFeedPolicyHash", feed_policy_hash(keys, state, base)),
        ("quoteFeedPolicyHash", feed_policy_hash(keys, state, quote)),
        ("baseSpreadBps", md["baseSpreadBps"]), ("skewSpreadBps", md["skewSpreadBps"]),
        ("maxTradeBps", md["maxTradeBps"]), ("minLiquidity", md["minLiquidity"]),
        ("firstDepositToleranceBps", md["firstDepositToleranceBps"]),
        ("depthFloorQuote", md["depthFloorQuote"]),
        ("minTicketQuote", md["minTicketQuote"]),
        ("seedBase", seed_base), ("seedQuote", seed_quote),
        ("seedInitialShares", md["seedInitialShares"]),
        ("lockBeneficiaryPubKey", sponsor["public"]),
        ("lockMinBlocks", md["lockMinBlocks"]), ("lockUntilHeight", lock_until),
        ("bookDefaultExpiryBlocks", md["bookDefaultExpiryBlocks"]),
        ("bookMaxExpiryBlocks", md["bookMaxExpiryBlocks"]),
        ("maxPairAgeBlocks", md["maxPairAgeBlocks"]),
    ]
    values = [str(value) for _, value in fields]
    terms = "{" + ", ".join(f'"{key}": {rholang_value(value)}' for key, value in fields) + "}"
    values_literal = "[" + ", ".join(json.dumps(value) for value in values) + "]"
    terms_hash = canonical("rcash:market-terms:v4", values)
    payload = f"rcash:market-create:v1|{market_id}|{terms_hash}|{sponsor['public']}"
    sig = sign_payload.sign_payload(sponsor["secret"], payload.encode())["signature"]
    term = (
        "new rl(`rho:registry:lookup`), ch, r, deployId(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{state['market_factory_uri']}`, *ch) |\n"
        "  for (MarketFactory <- ch) {\n"
        f'    MarketFactory!("createMarket", {terms}, {values_literal}, '
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
    created = one(minify(term), keys["deployer"]["secret"])
    if not isinstance(created, list) or len(created) < 4:
        raise RuntimeError(f"createMarket {market_id} failed: {created}")
    return {
        "market": {"marketId": created[0], "base": base, "quote": quote,
                   "status": "draft", "termsHash": created[3]},
        "slot": {"poolUri": created[1], "lockUri": created[2]},
        "terms": dict(fields),
        "created": True,
    }


def seed_market(keys: dict, state: dict, config: dict, base: str, quote: str,
                market: dict) -> None:
    """Mint both native assets into the deployer account and seed the pool."""
    md = config["marketDefaults"]
    # Every mint below reads the asset's feed and REV's feed; refresh first so a
    # long provisioning run cannot age a price out between the read and the mint.
    publish_prices(keys, state, config, (base, quote, "REV"))
    terms = market.get("terms") or {}
    seed_base = int(terms.get("seedBase", 0))
    seed_quote = int(terms.get("seedQuote", 0))
    if seed_base <= 0 or seed_quote <= 0:
        # Reconstruct from the oracle if the market already existed.
        rate = pair_rate(keys, state, base, quote, md["maxPairAgeBlocks"])
        seed_quote = max(md["seedQuoteTarget"], md["depthFloorQuote"], md["minTicketQuote"] * 10)
        seed_base = max(1, seed_quote * 100_000_000 // rate)
    lock_until = int(terms.get("lockUntilHeight", node.height() + md["lockUntilBlocks"]))
    deployer = keys["deployer"]
    rev_price = pair_rate(keys, state, "REV", "USD", md["maxPairAgeBlocks"])
    base_entry = existing_currency(keys, state, base)
    quote_entry = existing_currency(keys, state, quote)
    if base_entry is None or quote_entry is None:
        raise RuntimeError(f"seed needs native systems for {base}/{quote}")
    for code, entry, amount in ((base, base_entry, seed_base), (quote, quote_entry, seed_quote)):
        price = pair_rate(keys, state, code, "USD", md["maxPairAgeBlocks"])
        value_usd = amount * price // 100_000_000
        numerator = value_usd * config["issuerDefaults"]["mcrBps"] * 3 * 100_000_000
        denominator = 10000 * rev_price
        collateral = max(1, (numerator + denominator - 1) // denominator)
        term = (ROOT / "harness/scenarios/stablecoin_mint_hold.rho").read_text()
        replacements = {
            "__ROOT_URI__": state["root_uri"],
            "__VAULT_URI__": entry["vaultUri"],
            "__PUBKEY__": deployer["public"],
            "__FUND__": str(collateral),
            "__COLLATERAL__": str(collateral),
            "__MINT__": str(amount),
            "__ASSET__": code,
        }
        for key, value in replacements.items():
            term = term.replace(key, value)
        minted = one(minify(term), deployer["secret"])
        if not minted or not isinstance(minted, list) or len(minted) < 2:
            raise RuntimeError(f"{code} seed mint failed: {minted}")

    add = (ROOT / "harness/scenarios/mesh_add_liquidity.rho").read_text()
    replacements = {
        "__ROOT_URI__": state["root_uri"],
        "__POOL_URI__": market["slot"]["poolUri"],
        "__LOCK_URI__": market["slot"]["lockUri"],
        "__PUBKEY__": deployer["public"],
        "__BASE__": base, "__QUOTE__": quote,
        "__BASE_AMT__": str(seed_base), "__QUOTE_AMT__": str(seed_quote),
        "__LOCK_UNTIL__": str(lock_until),
    }
    for key, value in replacements.items():
        add = add.replace(key, value)
    seeded = one(minify(add), deployer["secret"])
    if not seeded or not isinstance(seeded, list) or len(seeded) < 3:
        raise RuntimeError(f"{base}/{quote} seed liquidity failed: {seeded}")


def activate_market(keys: dict, state: dict, market_id: str) -> str:
    reply = one(call(state["market_index_uri"], "MarketIndex",
                     f'MarketIndex!("activate", "{market_id}", *r) | '
                     "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    if not reply or reply[0] is not True:
        raise RuntimeError(f"activate {market_id} failed: {reply}")
    return reply[1]
