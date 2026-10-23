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
from unit_feed import blake2b256, canonical  # noqa: E402
from unit_hub import setup_feed  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_v3 import call, check, decode, one  # noqa: E402

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
    root = state["root_uri"]
    secret = keys["deployer"]["secret"]
    sponsor = keys["sponsor"]["public"]
    currency = "V4T"
    params = ('{"mcrBps": 20000, "bonusBps": 800, "closeFactorBps": 5000, '
              '"ratePerBlock": 3171, "debtCeiling": 10000000000000, '
              '"minDebt": 1000000, "maxDebt": 10000000000000, '
              '"maxOracleAge": 50}')
    values = [currency, "20000", "800", "5000", "3171", "10000000000000",
              "1000000", "10000000000000", "50"]
    params_hash = blake2b256(canonical("rcash:stablecoin-params:v1", values))
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
    sc_uri, custody_uri, params_uri, vault_uri, att_reply = system
    attest = att_reply[1]
    check("stablecoin attestation", attest.get("currency"), currency)
    check("stablecoin params hash", attest.get("paramsHash"), params_hash)
    print(f"stablecoin: {sc_uri}")
    print(f"custody: {custody_uri}")
    print(f"vault book: {vault_uri}")

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

    sender_pub = keys["key15"]["public"]

    registry = state["oracle_registry_uri"]
    for code, price in (("REV", 5000000), ("V4T", 66666)):
        entry = one(call(registry, "OracleRegistry",
                         f'OracleRegistry!("feedEntry", "{code}", *r) | '
                         "for (@x <- r) { deployId!(x) }"), secret)
        if entry[0] is False:
            setup_feed(keys, root, registry, code, [price, price, price])

    sender_pub = keys["key12"]["public"]
    ops_text = (ROOT / "harness/scenarios/stablecoin_ops.rho").read_text()
    for key, value in {
        "__ROOT_URI__": root,
        "__VAULT_URI__": vault_uri,
        "__PUBKEY__": sender_pub,
        "__FUND__": "200000000",
        "__COLLATERAL__": "100000000",
        "__MINT__": "100000000",
    }.items():
        ops_text = ops_text.replace(key, value)
    ops_term = minify(ops_text)
    check("vault deposit/mint/repay/withdraw", one(ops_term, secret), "ops-ok")

    print(json.dumps({"stablecoin_uri": sc_uri, "custody_uri": custody_uri,
                      "params_uri": params_uri, "vault_uri": vault_uri,
                      "currency": currency}, indent=2))
    print("unit_stablecoin: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
