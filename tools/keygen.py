#!/usr/bin/env python3
"""Generate secp256k1 keys and REV addresses for the R-Cash devnet.

The derivation matches rchain-rust's `rholang/src/util/rev_address.rs`:
    eth_address = keccak256(uncompressed_pubkey[1:])[-20:]
    key_hash    = keccak256(eth_address)
    payload     = 0x00000000 || key_hash
    address     = base58(payload || blake2b256(payload)[:4])

Private keys are written to `.devnet/keys.json`, which is gitignored. Devnet only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from coincurve import PrivateKey
from Crypto.Hash import keccak

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# The funded deployer baked into RNodeRust/tools/devnet.sh (public there). Used only for installs.
DEPLOYER_KEY = "a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76"
DEPLOYER_ADDR = "11112VYAt8rUGNRRZX3eJdgagaAhtWTK8Js7F7X5iqddMVqyDTtYau"

DEFAULT_NAMES = [
    "reporter1", "reporter2", "reporter3",
    "admin1", "admin2", "admin3",
    "sponsor",
    "sender", "business", "recipient", "ramp",
]


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = ALPHABET[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + out


def keccak256(data: bytes) -> bytes:
    h = keccak.new(digest_bits=256)
    h.update(data)
    return h.digest()


def public_key(secret_hex: str) -> bytes:
    return PrivateKey(bytes.fromhex(secret_hex)).public_key.format(compressed=False)


def rev_address(pub65: bytes) -> str:
    if len(pub65) != 65 or pub65[0] != 4:
        raise ValueError("REV addresses need a 65-byte uncompressed public key")
    eth = keccak256(pub65[1:])[-20:]
    key_hash = keccak256(eth)
    payload = b"\x00\x00\x00\x00" + key_hash
    checksum = hashlib.blake2b(payload, digest_size=32).digest()[:4]
    return b58encode(payload + checksum)


def new_secret() -> str:
    return os.urandom(32).hex()


def record(name: str, secret_hex: str) -> dict:
    pub = public_key(secret_hex)
    return {
        "name": name,
        "secret": secret_hex,
        "public": pub.hex(),
        "address": rev_address(pub),
    }


def http_json(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw.strip() else {}


def faucet(address: str, base: str) -> dict:
    return http_json(f"{base}/api/v1/faucet", {"address": address})


def load_keys(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".devnet/keys.json")
    ap.add_argument("--count", type=int, default=len(DEFAULT_NAMES),
                    help="number of extra keys if names are not supplied")
    ap.add_argument("--names", default=",".join(DEFAULT_NAMES))
    ap.add_argument("--faucet", action="store_true", help="fund each address once")
    ap.add_argument("--http", default="http://localhost:40403")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    keys = load_keys(out)

    if "deployer" not in keys:
        rec = record("deployer", DEPLOYER_KEY)
        if rec["address"] != DEPLOYER_ADDR:
            raise SystemExit(f"deployer address mismatch: {rec['address']} != {DEPLOYER_ADDR}")
        keys["deployer"] = rec

    names = [n.strip() for n in args.names.split(",") if n.strip()]
    for name in names:
        if name not in keys:
            keys[name] = record(name, new_secret())

    for _ in range(max(0, args.count - len(names))):
        name = f"key{len(keys)}"
        keys[name] = record(name, new_secret())

    if args.faucet:
        for name, rec in keys.items():
            if name == "deployer":
                continue
            if rec.get("funded"):
                continue
            try:
                faucet(rec["address"], args.http)
                rec["funded"] = True
                print(f"faucet: {name} {rec['address']}")
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")
                if "already funded" in body:
                    rec["funded"] = True
                    print(f"faucet: {name} already funded")
                else:
                    print(f"faucet: {name} FAILED {e.code}: {body}", file=sys.stderr)
            except Exception as e:  # devnet down, etc.
                print(f"faucet: {name} FAILED {e}", file=sys.stderr)
            time.sleep(1.05)  # the faucet is rate-limited to one drip per second

    out.write_text(json.dumps(keys, indent=2) + "\n")
    print(f"wrote {out} ({len(keys)} keys)")
    for name, rec in keys.items():
        print(f"  {name:10s} {rec['address']}  {rec['public'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
