#!/usr/bin/env python3
"""Exercise CurrencyRegistry: sponsor-signed zone registration and refusals.

Creates a zone through ZoneFactory, registers it in CurrencyRegistry with the
sponsor key, reads the record, and checks duplicate, wrong-deployer, wrong-signature
and unregistered-zone refusals.

Usage:
    python3 harness/unit_currency.py
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
from unit_feed import blake2b256, canonical  # noqa: E402
from unit_v3 import call, check, one  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    factory = state["zone_factory_uri"]
    registry = state["currency_registry_uri"]
    sponsor = keys["sponsor"]["public"]
    deployer_secret = keys["deployer"]["secret"]
    sponsor_secret = keys["sponsor"]["secret"]
    currency = "Z" + chr(65 + node.height() % 26) + "Y"

    params = ('{"mcrBps": 20000, "bonusBps": 800, "closeFactorBps": 5000, '
              '"ratePerBlock": 3171, "debtCeiling": 10000000000000, '
              '"minDebt": 1000000, "maxDebt": 10000000000000}')
    values = [currency, "20000", "800", "5000", "3171",
              "10000000000000", "1000000", "10000000000000"]
    params_hash = blake2b256(canonical("rcash:zone-params:v3", values))
    zone_payload = f"rcash:zone-create:v3|{currency}|{params_hash}|{sponsor}"
    zone_sig = sign_payload.sign_payload(sponsor_secret,
                                         zone_payload.encode())["signature"]
    create_body = (
        f'ZoneFactory!("create", "{currency}", {params}, "{params_hash}", '
        f'"{sponsor}", "{zone_sig}".hexToBytes(), *r) |\n'
        "  for (@x <- r) { deployId!(x) }"
    )
    created = one(call(factory, "ZoneFactory", create_body), deployer_secret)
    check("currency zone created", created[0], True)
    zone_uri = created[1]

    debug_lookup = one(call(state["zone_directory_uri"], "ZoneDirectory",
                            f'ZoneDirectory!("lookup", "{currency}", *r) | '
                            "for (@x <- r) { deployId!(x) }"), deployer_secret)
    print("debug", currency, zone_uri, debug_lookup)

    bind_payload = (
        f"rcash:currency-bind:v3|{currency}|{zone_uri}|{params_hash}|{sponsor}"
    )
    bind_sig = sign_payload.sign_payload(sponsor_secret,
                                         bind_payload.encode())["signature"]

    def register_term(code: str, uri: str, sig: str) -> str:
        body = (
            f'Registry!("register", "{code}", "{uri}", "{params_hash}", '
            f'"{sponsor}", "{sig}".hexToBytes(), *deployerId, *r) |\n'
            "  for (@x <- r) {\n"
            "    match x {\n"
            '      (true, Nil) => deployId!("ok")\n'
            "      (false, why) => deployId!(why)\n"
            "    }\n"
            "  }"
        )
        return (
            "new rl(`rho:registry:lookup`), ch, r, "
            "deployerId(`rho:rchain:deployerId`), "
            f"deployId(`rho:rchain:deployId`) in {{\n  rl!(`{registry}`, *ch) |\n"
            f"  for (Registry <- ch) {{ {body} }}\n"
            "}"
        )

    check("currency register",
          one(register_term(currency, zone_uri, bind_sig), sponsor_secret), "ok")
    record = one(call(registry, "CurrencyRegistry",
                      f'CurrencyRegistry!("currency", "{currency}", *r) | '
                      "for (@x <- r) { deployId!(x) }"), deployer_secret)[1]
    check("currency record zone", record.get("zoneUri"), zone_uri)
    check("currency record status", record.get("status"), "active")

    check("currency duplicate",
          one(register_term(currency, zone_uri, bind_sig), sponsor_secret), "duplicate")
    check("currency wrong deployer",
          one(register_term(currency, zone_uri, bind_sig), deployer_secret), "bad sponsor")

    bad_sig = sign_payload.sign_payload(keys["admin1"]["secret"],
                                        bind_payload.encode())["signature"]
    check("currency wrong signature",
          one(register_term(currency, zone_uri, bad_sig), sponsor_secret),
          "bad sponsor signature")

    fake_uri = "rho:id:fakezone"
    fake_payload = (
        f"rcash:currency-bind:v3|{currency}|{fake_uri}|{params_hash}|{sponsor}"
    )
    fake_sig = sign_payload.sign_payload(sponsor_secret,
                                         fake_payload.encode())["signature"]
    check("currency unregistered zone",
          one(register_term(currency, fake_uri, fake_sig), sponsor_secret),
          "zone not registered")

    print("unit_currency: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
