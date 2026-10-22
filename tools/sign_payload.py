#!/usr/bin/env python3
"""Canonical payloads and DER secp256k1 signatures for R-Cash admin/oracle actions.

The Rholang side verifies `secp256k1Verify(blake2b256(payload), der_sig, pubkey)`.  The canonical
strings here are the contract of record; keep them byte-identical to the Rholang builders.
"""

from __future__ import annotations

import argparse
import hashlib
import json

from coincurve import PrivateKey

SHARD = "/root"
ORACLE_DOMAIN = "rcash:oracle:v1"
ADMIN_DOMAIN = "rcash:admin:v1"


def blake2b256(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=32).digest()


def sign_prehashed(secret_hex: str, digest: bytes) -> str:
    if len(digest) != 32:
        raise ValueError("secp256k1Verify needs a 32-byte prehash")
    return PrivateKey(bytes.fromhex(secret_hex)).sign(digest, hasher=None).hex()


def oracle_payload(currency: str, price: int, height: int, shard: str = SHARD) -> bytes:
    return f"{ORACLE_DOMAIN}|{shard}|{currency}|{price}|{height}".encode()


def admin_payload(component: str, nonce: int, action: str, args: list[object]) -> bytes:
    # Args are strings or integers. Strings may not contain '|' or ','; validate at the caller.
    body = ",".join(str(a) for a in args)
    return f"{ADMIN_DOMAIN}|{component}|{nonce}|{action}|{body}".encode()


def sign_payload(secret_hex: str, payload: bytes) -> dict:
    digest = blake2b256(payload)
    return {
        "payload": payload.decode(errors="replace"),
        "hash": digest.hex(),
        "signature": sign_prehashed(secret_hex, digest),
        "public": PrivateKey(bytes.fromhex(secret_hex)).public_key.format(compressed=False).hex(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="hex secp256k1 secret")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--payload", help="literal UTF-8 payload")
    g.add_argument("--oracle", nargs=3, metavar=("CURRENCY", "PRICE", "HEIGHT"))
    g.add_argument("--admin", nargs=3, metavar=("COMPONENT", "NONCE", "ACTION"),
                   help="args are passed with --args (comma-separated)")
    ap.add_argument("--args", default="")
    args = ap.parse_args(argv)

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
