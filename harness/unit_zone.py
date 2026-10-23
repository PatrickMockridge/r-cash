#!/usr/bin/env python3
"""Exercise ZoneTemplate, ZoneDirectory and ZoneFactory.

Creates an NGN zone from signed params, checks the directory and zone views,
opens a vault through AccountFactory, and checks the refusal paths.

Usage:
    python3 harness/unit_zone.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import sign_payload  # noqa: E402
from unit_feed import blake2b256, canonical  # noqa: E402
from unit_v3 import call, check, one  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    factory = state["zone_factory_uri"]
    directory = state["zone_directory_uri"]
    secret = keys["deployer"]["secret"]
    sponsor = keys["sponsor"]["public"]
    import deploy as node
    currency = "Z" + chr(65 + node.height() % 26) + "Z"

    params = ('{"mcrBps": 20000, "bonusBps": 800, "closeFactorBps": 5000, '
              '"ratePerBlock": 3171, "debtCeiling": 10000000000000, '
              '"minDebt": 1000000, "maxDebt": 10000000000000}')
    values = [currency, "20000", "800", "5000", "3171",
              "10000000000000", "1000000", "10000000000000"]
    params_hash = blake2b256(canonical("rcash:zone-params:v3", values))
    payload = f"rcash:zone-create:v3|{currency}|{params_hash}|{sponsor}"
    sig = sign_payload.sign_payload(keys["sponsor"]["secret"],
                                    payload.encode())["signature"]

    def create_term(params_map: str, params_hex: str, signature: str) -> str:
        body = (
            f'ZoneFactory!("create", "{currency}", {params_map}, "{params_hex}", '
            f'"{sponsor}", "{signature}".hexToBytes(), *r) |\n'
            "  for (@x <- r) { deployId!(x) }"
        )
        return call(factory, "ZoneFactory", body)

    created = one(create_term(params, params_hash, sig), secret)
    check("zone factory created", created[0], True)
    zone_uri = created[1]
    attest = created[2][1]
    check("zone attestation currency", attest.get("currency"), currency)
    check("zone attestation hash", attest.get("paramsHash"), params_hash)
    check("zone attestation template", attest.get("template"), "rcash:currency-zone:v3")

    lookup = one(call(directory, "ZoneDirectory",
                      f'ZoneDirectory!("lookup", "{currency}", *r) | '
                      "for (@x <- r) { deployId!(x) }"), secret)
    check("zone directory uri", lookup, (True, zone_uri))

    currency_result = one(call(zone_uri, "CurrencyZone",
                        'CurrencyZone!(["currency"], *r) | '
                        "for (@x <- r) { deployId!(x) }"), secret)
    check("zone currency", currency_result, (True, currency))
    zone_params = one(call(zone_uri, "CurrencyZone",
                           'CurrencyZone!(["params"], *r) | '
                           "for (@x <- r) { deployId!(x) }"), secret)
    check("zone params mcr", zone_params[1].get("mcrBps"), 20000)
    vaults = one(call(zone_uri, "CurrencyZone",
                      'CurrencyZone!(["vaults"], *r) | '
                      "for (@x <- r) { deployId!(x) }"), secret)
    check("zone empty vaults", vaults, (True, []))

    duplicate = one(create_term(params, params_hash, sig), secret)
    check("zone duplicate", duplicate, (False, "duplicate"))

    bad_sig = sign_payload.sign_payload(keys["admin1"]["secret"],
                                        payload.encode())["signature"]
    bad = one(create_term(params, params_hash, bad_sig), secret)
    check("zone bad signature", bad, (False, "bad sponsor signature"))

    other_values = list(values)
    other_values[1] = "20001"
    other_hash = blake2b256(canonical("rcash:zone-params:v3", other_values))
    other_payload = f"rcash:zone-create:v3|{currency}|{other_hash}|{sponsor}"
    other_sig = sign_payload.sign_payload(keys["sponsor"]["secret"],
                                          other_payload.encode())["signature"]
    mismatch = one(create_term(params, other_hash, other_sig), secret)
    check("zone params hash", mismatch, (False, "params hash"))

    print("unit_zone: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
