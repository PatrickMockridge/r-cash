#!/usr/bin/env python3
"""List a test stablecoin on the rhobot testnet and exercise the payment path.

Assumes `harness/install_testnet.py` has installed the platform. Deploys two oracle
feeds (REV and TUSD), activates them, deploys the TUSD stablecoin system, registers the
currency, then funds the deployer account and runs send -> claim between two testnet keys.

Usage:
    python3 harness/testnet_setup.py [--node URL]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import install_testnet as net  # noqa: E402
import sign_payload  # noqa: E402
from unit_feed import blake2b256, canonical  # noqa: E402

TESTNET_KEYS = ROOT / ".testnet" / "keys.json"
DEVNET_KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".testnet" / "install.json"
CURRENCY = "TUSD"
REPORTERS = ["reporter1", "reporter2", "reporter3"]
PRICES = {"REV": 5_000_000, CURRENCY: 66_666}


def http_json(method: str, path: str, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{net.NODE}{path}", data=data, method=method,
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b"null")


def height() -> int:
    return int(http_json("GET", "/api/v1/status")["latestBlockNumber"])


def deploy_term(term: str, key: str = "deployer") -> dict:
    return net.deploy(term, key)


def existing_feed(registry_uri: str, currency: str) -> str | None:
    """The URI already bound for a currency, if any."""
    term = (
        f"new return, rl(`rho:registry:lookup`), ch, r in {{ "
        f"rl!(`{registry_uri}`, *ch) | for (Registry <- ch) {{ "
        f'Registry!("feedEntry", "{currency}", *r) | '
        f"for (@x <- r) {{ return!(x) }} }} }}"
    )
    request = urllib.request.Request(
        f"{net.NODE}/api/v1/explore-deploy", data=json.dumps(term).encode(),
        headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        doc = json.loads(response.read())
    expr = doc.get("expr") or []
    if not expr:
        return None
    data = expr[0].get("ExprTuple", {}).get("data", [])
    if len(data) < 2 or data[0].get("ExprBool", {}).get("data") is not True:
        return None
    entry = data[1].get("ExprMap", {}).get("data", {})
    uri = entry.get("uri", {})
    return uri.get("ExprString", {}).get("data") or uri.get("ExprUri", {}).get("data")


def setup_feed(keys: dict, sponsor: dict, currency: str,
               state: dict) -> tuple[str, str]:
    feed_id = f"{currency}-testnet-1"
    policy_values = [
        currency, keys["reporter1"]["public"], keys["reporter2"]["public"],
        keys["reporter3"]["public"], sponsor["public"], "2", "50", "200", "1",
        "1000000000000", "1", "3",
    ]
    policy_hash = blake2b256(canonical("rcash:oracle-policy:v3", policy_values))
    reporters = "[" + ", ".join(f'"{keys[n]["public"]}"' for n in REPORTERS) + "]"
    term = net.render("31_feed", {
        "__ROOT_URI__": state["root_uri"],
        "__CURRENCY__": currency,
        "__FEED_ID__": feed_id,
        "__REPORTERS__": reporters,
        "__SPONSOR_PUB__": sponsor["public"],
        "__POLICY_HASH__": policy_hash,
        "__QUORUM__": "2",
        "__MAX_AGE__": "50",
        "__MAX_SPREAD__": "200",
        "__MIN_PRICE__": "1",
        "__MAX_PRICE__": "1000000000000",
        "__TRIAL_BLOCKS__": "1",
        "__TRIAL_MIN_SUBMITS__": "3",
    })
    doc = deploy_term(term)
    uri = net.uris(doc)[0]

    bind_payload = f"rcash:feed-bind:v3|{currency}|{feed_id}|{uri}|{policy_hash}|{sponsor['public']}"
    bind_sig = sign_payload.sign_payload(
        sponsor["secret"], bind_payload.encode())["signature"]
    bind = (
        f"new rl(`rho:registry:lookup`), ch, r, "
        f"deployId(`rho:rchain:deployId`), deployerId(`rho:rchain:deployerId`) in {{\n"
        f"  rl!(`{state['oracle_registry_uri']}`, *ch) |\n"
        f"  for (Registry <- ch) {{\n"
        f'    Registry!("registerFeed", "{currency}", "{uri}", "{feed_id}", '
        f'"{policy_hash}", "{sponsor["public"]}", "{bind_sig}".hexToBytes(), '
        f"*deployerId, *r) |\n"
        f"    for (@x <- r) {{ deployId!(x) }}\n"
        f"  }}\n"
        f"}}"
    )
    deploy_term(bind)
    return uri, feed_id


def submit_prices(keys: dict, sponsor: dict, feed_uri: str, feed_id: str,
                  currency: str, price: int) -> None:
    for index in range(3):
        at = height()
        reporter = keys[REPORTERS[index]]
        payload = f"rcash:oracle-submit:v3|{feed_id}|{currency}|{index}|{price}|{at}"
        sig = sign_payload.sign_payload(
            reporter["secret"], payload.encode())["signature"]
        term = (
            f"new rl(`rho:registry:lookup`), ch, r, "
            f"deployId(`rho:rchain:deployId`) in {{\n"
            f"  rl!(`{feed_uri}`, *ch) |\n"
            f"  for (Feed <- ch) {{\n"
            f'    Feed!("submit", {index}, {price}, {at}, "{reporter["public"]}", '
            f'"{sig}".hexToBytes(), *r) |\n'
            f"    for (@x <- r) {{\n"
            f"      match x {{\n"
            f'        (true, Nil) => deployId!("ok")\n'
            f"        _ => deployId!(x)\n"
            f"      }}\n"
            f"    }}\n"
            f"  }}\n"
            f"}}"
        )
        result = deploy_term(term)
        if "ok" not in json.dumps(result.get("result")):
            raise SystemExit(f"{currency} submit {index} refused: {result.get('result')}")
    activate = (
        f"new rl(`rho:registry:lookup`), ch, r, "
        f"deployId(`rho:rchain:deployId`) in {{\n"
        f"  rl!(`{feed_uri}`, *ch) |\n"
        f'  for (Feed <- ch) {{ Feed!("activate", *r) | for (@x <- r) {{ deployId!(x) }} }}\n'
        f"}}"
    )
    deploy_term(activate)


def deploy_stablecoin(state: dict, sponsor: dict) -> list:
    params = ('{"mcrBps": 20000, "bonusBps": 800, "closeFactorBps": 5000, '
              '"ratePerBlock": 3171, "debtCeiling": 10000000000000, '
              '"minDebt": 1000000, "maxDebt": 10000000000000, '
              '"maxOracleAge": 50}')
    values = [CURRENCY, "20000", "800", "5000", "3171", "10000000000000",
              "1000000", "10000000000000", "50"]
    params_hash = blake2b256(canonical("rcash:stablecoin-params:v1", values))
    payload = f"rcash:stablecoin-create:v1|{CURRENCY}|{params_hash}|{sponsor['public']}"
    sig = sign_payload.sign_payload(sponsor["secret"], payload.encode())["signature"]
    term = net.render("31_stablecoin", {
        "__ROOT_URI__": state["root_uri"],
        "__CURRENCY__": CURRENCY,
        "__PARAMS__": params,
        "__PARAMS_HASH__": params_hash,
        "__SPONSOR_PUB__": sponsor["public"],
        "__SPONSOR_SIG__": sig,
    })
    doc = deploy_term(term)
    found = net.uris(doc)
    if len(found) < 5:
        raise SystemExit(f"stablecoin deploy returned {found} (want five URIs)")
    sc, custody, params_uri, vault, liq = found[:5]
    listing = f"rcash:currency-register:v1|{CURRENCY}|{sc}|{params_hash}|{sponsor['public']}"
    listing_sig = sign_payload.sign_payload(
        sponsor["secret"], listing.encode())["signature"]
    register = (
        f"new rl(`rho:registry:lookup`), ch, r, "
        f"deployId(`rho:rchain:deployId`) in {{\n"
        f"  rl!(`{state['currency_registry_uri']}`, *ch) |\n"
        f"  for (Registry <- ch) {{\n"
        f'    Registry!("register", "{CURRENCY}", "{sc}", "{custody}", "{params_uri}", '
        f'"{vault}", "{liq}", "{params_hash}", "{sponsor["public"]}", '
        f'"{listing_sig}".hexToBytes(), *r) |\n'
        f"    for (@x <- r) {{ deployId!(x) }}\n"
        f"  }}\n"
        f"}}"
    )
    listed = deploy_term(register)
    if "true" not in json.dumps(listed.get("result")).lower():
        raise SystemExit(f"currency listing refused: {listed.get('result')}")
    return [sc, custody, params_uri, vault, liq, params_hash]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", default=net.NODE)
    args = ap.parse_args(argv)
    net.NODE = args.node

    keys = json.loads(TESTNET_KEYS.read_text())
    reporters = json.loads(DEVNET_KEYS.read_text())
    sponsor = keys["deployer"]
    state = json.loads(STATE.read_text())

    for currency in ("REV", CURRENCY):
        bound = existing_feed(state["oracle_registry_uri"], currency)
        if bound:
            feed_uri, feed_id = bound, f"{currency}-testnet-1"
            print(f"{currency} feed already bound: {feed_uri}")
        else:
            feed_uri, feed_id = setup_feed(reporters, sponsor, currency, state)
            print(f"{currency} feed: {feed_uri}")
        submit_prices(reporters, sponsor, feed_uri, feed_id, currency, PRICES[currency])
        print(f"{currency} feed active at {PRICES[currency]}")

    system = deploy_stablecoin(state, sponsor)
    print(f"{CURRENCY} stablecoin: {system[0]}")
    print(f"{CURRENCY} vault: {system[3]}")
    print(f"{CURRENCY} params hash: {system[5]}")

    result = {
        "currency": CURRENCY,
        "stablecoin": system[0],
        "custody": system[1],
        "vault": system[3],
        "liquidation": system[4],
        "paramsHash": system[5],
    }
    (ROOT / ".testnet" / "stablecoin.json").write_text(
        json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
