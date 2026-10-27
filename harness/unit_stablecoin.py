#!/usr/bin/env python3
"""Exercise the v0.4 REV-backed stablecoin system.

Deploys one currency system from signed params and checks the issuer, custody,
parameters and vault-book views. Vault operations are added incrementally.

Usage:
    python3 harness/unit_stablecoin.py
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
from install_v3 import render  # noqa: E402
from feed_refresh import feed_uri, set_price  # noqa: E402
from unit_feed import blake2b256, canonical  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_v3 import call, check, decode, faucet_top_up, one  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"
PHLO = 100_000_000


def deploy_system(term: str, secret: str) -> list:
    deploy_id = node.deploy(term, secret, phlo_limit=PHLO)
    variant, payload = node.wait_processed(deploy_id, timeout=300)
    if variant != "processedwithsuccess":
        raise AssertionError(f"stablecoin deploy {variant}: {json.dumps(payload)[:3000]}")
    block = payload.get("block") or {}
    if block.get("blockHash"):
        node.wait_finalized(block["blockHash"])
    result = decode(payload.get("deployResult"))
    if not result:
        raise AssertionError("stablecoin deploy returned no result")
    return result[0]


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    if "currency_registry_uri" not in state:
        steps = state.get("steps", {})
        state["currency_registry_uri"] = steps["currency_registry"]["uris"][1]
        state["stablecoin_directory_uri"] = steps["currency_registry"]["uris"][0]
    root = state["root_uri"]
    secret = keys["deployer"]["secret"]
    for name in ("key12", "key13", "key14"):
        faucet_top_up(keys[name]["address"])
    sponsor = keys["sponsor"]["public"]
    currency = "V4T"
    params = ('{"mcrBps": 20000, "bonusBps": 800, "closeFactorBps": 5000, '
              '"ratePerBlock": 3171, "debtCeiling": 10000000000000, '
              '"minDebt": 1000000, "maxDebt": 10000000000000, '
              '"maxOracleAge": 50, "savingsShareBps": 5000, "psmFeeBps": 10}')
    values = [currency, "20000", "800", "5000", "3171", "10000000000000",
              "1000000", "10000000000000", "50", "5000", "10"]
    params_hash = blake2b256(canonical("rcash:stablecoin-params:v2", values))
    payload = f"rcash:stablecoin-create:v1|{currency}|{params_hash}|{sponsor}"
    sig = sign_payload.sign_payload(keys["sponsor"]["secret"],
                                    payload.encode())["signature"]
    term = render("31_stablecoin", {
        "__ROOT_URI__": root,
        "__CURRENCY__": currency,
        "__PARAMS__": params,
        "__PARAMS_HASH__": params_hash,
        "__SPONSOR_PUB__": sponsor,
        "__SPONSOR_SIG__": sig,
    })
    system = deploy_system(term, secret)
    (sc_uri, custody_uri, params_uri, vault_uri, liq_uri, savings_uri,
     psm_uri, buffer_uri, att_reply) = system
    attest = att_reply[1]
    check("stablecoin attestation", attest.get("currency"), currency)
    check("stablecoin params hash", attest.get("paramsHash"), params_hash)
    print(f"stablecoin: {sc_uri}")
    print(f"custody: {custody_uri}")
    print(f"vault book: {vault_uri}")
    print(f"liquidation engine: {liq_uri}")

    supply = one(call(sc_uri, "Stablecoin",
                      'Stablecoin!("supply", *r) | for (@x <- r) { deployId!(x) }'),
                 secret)
    check("stablecoin initial supply", supply, (True, 0))
    vault_params = one(call(vault_uri, "VaultBook",
                            'VaultBook!("params", *r) | for (@x <- r) { deployId!(x) }'),
                       secret)[1]
    check("vault params mcr", vault_params.get("mcrBps"), 20000)
    vault_attest = one(call(vault_uri, "VaultBook",
                            'VaultBook!("attest", *r) | for (@x <- r) { deployId!(x) }'),
                       secret)[1]
    check("vault attestation", vault_attest.get("currency"), currency)
    custody_attest = one(call(custody_uri, "CollateralCustody",
                              'CollateralCustody!("attest", *r) | '
                              "for (@x <- r) { deployId!(x) }"), secret)[1]
    check("custody attestation", custody_attest.get("currency"), currency)

    # Currency listing: sponsor signature + live attestation + directory.
    currency_registry = state["currency_registry_uri"]
    directory = state["stablecoin_directory_uri"]
    listing = (f"rcash:currency-register:v3|{currency}|{sc_uri}|{custody_uri}|"
               f"{params_uri}|{vault_uri}|{liq_uri}|{savings_uri}|{psm_uri}|"
               f"{buffer_uri}|{params_hash}|{sponsor}")
    listing_sig = sign_payload.sign_payload(keys["sponsor"]["secret"],
                                            listing.encode())["signature"]
    register_body = (
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
    listed = one(call(currency_registry, "CurrencyRegistry", register_body), secret)
    fresh_listing = listed[0] is True
    if fresh_listing:
        check("currency entry status", listed[1].get("status"), "active")
        check("currency entry stablecoin", listed[1].get("stablecoinUri"), sc_uri)
        check("currency entry savings", listed[1].get("savingsUri"), savings_uri)
        check("currency entry psm", listed[1].get("psmUri"), psm_uri)
        check("currency entry buffer", listed[1].get("bufferUri"), buffer_uri)
    else:
        # One system per currency: a previous run on this chain already listed it.
        print("currency already listed; checking the existing entry")
    entry = one(call(currency_registry, "CurrencyRegistry",
                     f'CurrencyRegistry!("currency", "{currency}", *r) | '
                     "for (@x <- r) { deployId!(x) }"), secret)
    check("currency lookup", entry[0], True)
    if fresh_listing:
        check("currency lookup vault", entry[1].get("vaultUri"), vault_uri)
    directory_entry = one(call(directory, "StablecoinDirectory",
                               f'StablecoinDirectory!("lookup", "{currency}", *r) | '
                               "for (@x <- r) { deployId!(x) }"), secret)
    check("directory lookup", directory_entry[0], True)
    if fresh_listing:
        check("directory lookup liquidation", directory_entry[1].get("liquidationUri"), liq_uri)

    duplicate = one(call(currency_registry, "CurrencyRegistry", register_body), secret)
    check("duplicate listing refused", duplicate[0], False)

    bad_listing = (f"rcash:currency-register:v3|V4U|{sc_uri}|{custody_uri}|"
                   f"{params_uri}|{vault_uri}|{liq_uri}|{savings_uri}|{psm_uri}|"
                   f"{buffer_uri}|{params_hash}|{sponsor}")
    bad_sig = sign_payload.sign_payload(keys["reporter1"]["secret"],
                                        bad_listing.encode())["signature"]
    bad_body = (
        f'CurrencyRegistry!("register", "V4U", "{sc_uri}", "{custody_uri}", '
        f'"{params_uri}", "{vault_uri}", "{liq_uri}", "{savings_uri}", "{psm_uri}", '
        f'"{buffer_uri}", "{params_hash}", "{sponsor}", '
        f'"{bad_sig}".hexToBytes(), *r) |\n'
        "  for (@x <- r) {\n"
        "    match x {\n"
        '      (true, entry) => deployId!([true, entry])\n'
        "      (false, why) => deployId!([false, why])\n"
        "      _ => deployId!(x)\n"
        "    }\n"
        "  }"
    )
    refused = one(call(currency_registry, "CurrencyRegistry", bad_body), secret)
    check("bad sponsor signature refused", refused, [False, "bad sponsor signature"])

    def set_paused(nonce: int, paused: bool) -> str:
        args = "true" if paused else "false"
        payload = f"rcash:admin:v1|stablecoin:{currency}|{nonce}|setPaused|{args}"
        sigs = ", ".join(
            f'"{sign_payload.sign_payload(keys[n]["secret"], payload.encode())["signature"]}".hexToBytes()'
            for n in ("admin1", "admin2"))
        body = (
            f'CurrencyRegistry!("setPaused", "{currency}", {str(paused).lower()}, '
            f"{nonce}, [{sigs}], *r) |\n"
            "  for (@x <- r) {\n"
            "    match x {\n"
            '      (true, status) => deployId!(status)\n'
            "      (false, why) => deployId!(why)\n"
            "    }\n"
            "  }"
        )
        return one(call(currency_registry, "CurrencyRegistry", body), secret)

    pause_nonce = node.height()
    check("pause currency", set_paused(pause_nonce, True), "paused")
    paused = one(call(currency_registry, "CurrencyRegistry",
                      f'CurrencyRegistry!("currency", "{currency}", *r) | '
                      "for (@x <- r) { deployId!(x) }"), secret)[1]
    check("currency paused", paused.get("status"), "paused")
    check("resume currency", set_paused(pause_nonce + 1, False), "active")

    registry = state["oracle_registry_uri"]
    rev_feed = feed_uri(keys, root, registry, "REV", [5000000] * 3)
    v4t_feed = feed_uri(keys, root, registry, "V4T", [66666] * 3)
    set_price(keys, v4t_feed, "V4T", 66666)
    set_price(keys, rev_feed, "REV", 5000000)

    # Savings: mint, route through the account, deposit, withdraw and repay.
    savings_uri = system[5]
    savings_text = (ROOT / "harness/scenarios/stablecoin_savings.rho").read_text()
    for key, value in {
        "__ROOT_URI__": root,
        "__VAULT_URI__": vault_uri,
        "__SAVINGS_URI__": savings_uri,
        "__PUBKEY__": keys["key13"]["public"],
        "__FUND__": "15000000",
        "__COLLATERAL__": "8000000",
        "__MINT__": "100000000",
    }.items():
        savings_text = savings_text.replace(key, value)
    savings_result = one(minify(savings_text), keys["key13"]["secret"])
    if isinstance(savings_result, tuple) and savings_result[0] is False:
        print("savings raw:", savings_result)
    check("savings shares", savings_result[0], 100000000)
    check("savings withdrawn", savings_result[1], 100000000)

    # PSM: fund the REV buffer, mint a stablecoin, redeem it at the oracle rate.
    psm_uri = system[6]
    psm_text = (ROOT / "harness/scenarios/stablecoin_psm.rho").read_text()
    for key, value in {
        "__ROOT_URI__": root,
        "__VAULT_URI__": vault_uri,
        "__PSM_URI__": psm_uri,
        "__PUBKEY__": keys["key14"]["public"],
        "__FUND__": "15000000",
        "__COLLATERAL__": "8000000",
        "__MINT__": "100000000",
        "__PSM_REV__": "5000000",
    }.items():
        psm_text = psm_text.replace(key, value)
    psm_result = one(minify(psm_text), keys["key14"]["secret"])
    check("psm redemption", psm_result[0] > 0, True)

    sender_pub = keys["key12"]["public"]
    sender_secret = keys["key12"]["secret"]
    ops_text = (ROOT / "harness/scenarios/stablecoin_ops.rho").read_text()
    for key, value in {
        "__ROOT_URI__": root,
        "__VAULT_URI__": vault_uri,
        "__PUBKEY__": sender_pub,
        "__FUND__": "15000000",
        "__COLLATERAL__": "8000000",
        "__MINT__": "100000000",
    }.items():
        ops_text = ops_text.replace(key, value)
    ops_term = minify(ops_text)
    check("vault deposit/mint/repay/withdraw", one(ops_term, sender_secret), "ops-ok")

    print(json.dumps({"stablecoin_uri": sc_uri, "custody_uri": custody_uri,
                      "params_uri": params_uri, "vault_uri": vault_uri,
                      "currency": currency}, indent=2))
    print("unit_stablecoin: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
