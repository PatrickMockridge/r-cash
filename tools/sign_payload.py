#!/usr/bin/env python3
"""Canonical payloads and DER secp256k1 signatures for R-Cash admin/oracle actions.

The Rholang side verifies `secp256k1Verify(blake2b256(payload), der_sig, pubkey)`.  The canonical
strings here are the contract of record; keep them byte-identical to the Rholang builders.

Canonical encoding (OCAP-09): the same length-prefixed form as `Codec` in
`contracts/src/deploy/v3/01_kernel.rho`:

    schema|LEN:value|LEN:value|...

`LEN` is the number of characters in the value (Rholang `String.length()` counts
Unicode scalar values, RCHIP #37; Python `len` counts the same).  The prefix makes
the encoding unambiguous even when a value contains `|`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Sequence

SHARD = "/root"
ORACLE_DOMAIN = "rcash:oracle:v1"
ADMIN_DOMAIN = "rcash:admin:v1"

# Schema-version constants. The string is the first field of the canonical
# preimage and is never length-prefixed.
ADMIN_SCHEMA = "rcash:admin:v1"
ORACLE_SUBMIT_SCHEMA = "rcash:oracle-submit:v3"
FEED_BIND_SCHEMA = "rcash:feed-bind:v3"
MARKET_CREATE_SCHEMA = "rcash:market-create:v1"
MARKET_TERMS_SCHEMA = "rcash:market-terms:v4"
MARKET_AUTH_SCHEMA = "rcash:market-auth:v1"
PROVISION_SCHEMA = "rcash:provision:v1"


def blake2b256(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=32).digest()


def canonical(schema: str, values: Sequence[str | int]) -> str:
    """Return `schema|len:value|...` exactly as Rholang's `Codec@"canonical"` does.

    Values are stringified with `str`; pass integers where the contract builds
    them with `.toString()`.  An empty sequence encodes as the bare schema.
    """
    parts = [schema]
    for value in values:
        text = str(value)
        parts.append(f"{len(text)}:{text}")
    return "|".join(parts)


def hash_canonical(schema: str, values: Sequence[str | int]) -> bytes:
    """Blake2b-256 of the canonical UTF-8 bytes (`Codec@"hash"`)."""
    return blake2b256(canonical(schema, values).encode("utf-8"))


def hash_canonical_hex(schema: str, values: Sequence[str | int]) -> str:
    return hash_canonical(schema, values).hex()


def sign_prehashed(secret_hex: str, digest: bytes) -> str:
    if len(digest) != 32:
        raise ValueError("secp256k1Verify needs a 32-byte prehash")
    from coincurve import PrivateKey

    return PrivateKey(bytes.fromhex(secret_hex)).sign(digest, hasher=None).hex()


def oracle_payload(currency: str, price: int, height: int, shard: str = SHARD) -> bytes:
    """Legacy v0.3 oracle submit preimage (kept for the legacy harness)."""
    return f"{ORACLE_DOMAIN}|{shard}|{currency}|{price}|{height}".encode()


def admin_canonical_payload(domain: str, nonce: int, action: str,
                            args_hash: str) -> bytes:
    """Canonical admin preimage verified by `AdminGuard@"verify"`."""
    return canonical(ADMIN_SCHEMA, [domain, nonce, action, args_hash]).encode()


def admin_payload(component: str, nonce: int, action: str,
                  args: list[object]) -> bytes:
    """Legacy v0.3 admin preimage (kept byte-identical for existing callers)."""
    # Args are strings or integers. Strings may not contain '|' or ','; validate at the caller.
    body = ",".join(str(a) for a in args)
    return f"{ADMIN_DOMAIN}|{component}|{nonce}|{action}|{body}".encode()


def oracle_submit_payload(feed_id: str, currency: str, index: int,
                          price: int, height: int) -> bytes:
    """Canonical reporter preimage verified by `OracleFeed@"submit"`."""
    return canonical(ORACLE_SUBMIT_SCHEMA,
                     [feed_id, currency, index, price, height]).encode()


def feed_bind_payload(code: str, feed_id: str, feed_uri: str,
                      policy_hash: str, sponsor_hex: str) -> bytes:
    """Canonical sponsor preimage verified by `OracleRegistry@"registerFeed"`."""
    return canonical(FEED_BIND_SCHEMA,
                     [code, feed_id, feed_uri, policy_hash, sponsor_hex]).encode()


def market_create_payload(market_id: str, terms_hash: str,
                          sponsor_hex: str) -> bytes:
    """Canonical sponsor preimage verified by the market factory/terms store."""
    return canonical(MARKET_CREATE_SCHEMA,
                     [market_id, terms_hash, sponsor_hex]).encode()


def sign_payload(secret_hex: str, payload: bytes) -> dict:
    from coincurve import PrivateKey

    digest = blake2b256(payload)
    return {
        "payload": payload.decode(errors="replace"),
        "hash": digest.hex(),
        "signature": sign_prehashed(secret_hex, digest),
        "public": PrivateKey(bytes.fromhex(secret_hex)).public_key.format(compressed=False).hex(),
    }


def self_check() -> None:
    """Checked examples for the canonical encoding.

    The market-terms example is the vector shared with the Rholang `Codec` and
    the Rust reference; the admin example proves a `|` inside a value cannot
    shift the field boundary.
    """
    assert canonical("rcash:market-terms:v4", ["KES/NGN:v1", "KES-NGN-v1", "NGN"]) == (
        "rcash:market-terms:v4|10:KES/NGN:v1|10:KES-NGN-v1|3:NGN"
    )
    assert canonical(ADMIN_SCHEMA, ["market-index", 7, "setStatus",
                                    "REV/V4T:v1|paused"]) == (
        "rcash:admin:v1|12:market-index|1:7|9:setStatus|17:REV/V4T:v1|paused"
    )
    assert canonical(ADMIN_SCHEMA, []) == ADMIN_SCHEMA
    assert hash_canonical("rcash:market-terms:v4", ["a"]).hex() == blake2b256(
        b"rcash:market-terms:v4|1:a").hex()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", help="hex secp256k1 secret")
    ap.add_argument("--self-check", action="store_true",
                    help="verify the canonical encoding examples and exit")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--payload", help="literal UTF-8 payload")
    g.add_argument("--oracle", nargs=3, metavar=("CURRENCY", "PRICE", "HEIGHT"))
    g.add_argument("--admin", nargs=3, metavar=("COMPONENT", "NONCE", "ACTION"),
                   help="args are passed with --args (comma-separated)")
    ap.add_argument("--args", default="")
    args = ap.parse_args(argv)

    if args.self_check:
        self_check()
        print("sign_payload canonical: ok")
        return 0
    if not args.key:
        ap.error("--key is required unless --self-check is given")

    if args.payload is not None:
        payload = args.payload.encode()
    elif args.oracle is not None:
        currency, price, height = args.oracle
        payload = oracle_payload(currency, int(price), int(height))
    else:
        component, nonce, action = args.admin
        payload = admin_payload(component, int(nonce), action,
                                [a for a in args.args.split(",") if a])
    print(json.dumps(sign_payload(args.key, payload), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
