#!/usr/bin/env python3
"""Canonical market terms, zone params, feed policy, pool and book params.

Rholang, Rust and Python must produce byte-identical canonical strings. This tool is
the Python reference; `--check` compares it with tests/terms/terms-vectors.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VECTORS = ROOT / "tests" / "terms" / "terms-vectors.json"

TERMS_SCHEMA = "rcash:market-terms:v4"
ZONE_SCHEMA = "rcash:zone-params:v1"
FEED_SCHEMA = "rcash:oracle-policy:v3"
POOL_SCHEMA = "rcash:pool-params:v1"
BOOK_SCHEMA = "rcash:book-params:v4"


def canonical(schema: str, values: list[str | int]) -> str:
    encoded = [f"{len(str(v).encode('utf-8'))}:{v}" for v in values]
    return "|".join([schema, *encoded])


def digest(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=32).hexdigest()


def sample() -> dict:
    zone_values = [20000, 800, 5000, 3171, 10_000_000_000_000, 1_000_000, 10_000_000_000_000]
    feed_values = [2, 50, 200, 1, 1_000_000_000_000, 10, 4]
    pool_values = [20, 80, 500, 100_000_000, 100, 130_000_000_000, 1_300_000_000]
    book_values = [720, 129_600, 1, 128, 64, 100_000_000]
    terms_values = [
        "KES/NGN:v1",
        "KES-NGN-v1",
        "NGN",
        "KES",
        1,
        "04aa",
        "1111sponsor",
        "11" * 32,
        "22" * 32,
        20,
        80,
        500,
        100_000_000,
        100,
        130_000_000_000,
        1_300_000_000,
        1_500_000_000_000,
        130_000_000_000,
        2_000_000_000,
        "04aa",
        302_400,
        500_000,
        720,
        129_600,
        50,
    ]

    def entry(schema: str, values: list) -> dict:
        text = canonical(schema, values)
        return {"values": [str(v) for v in values], "canonical": text, "hash": digest(text)}

    return {
        "zone": entry(ZONE_SCHEMA, zone_values),
        "feed": entry(FEED_SCHEMA, feed_values),
        "pool": entry(POOL_SCHEMA, pool_values),
        "book": entry(BOOK_SCHEMA, book_values),
        "terms": entry(TERMS_SCHEMA, terms_values),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write the vectors file")
    parser.add_argument("--check", action="store_true", help="verify the vectors file")
    args = parser.parse_args()

    actual = sample()
    if args.write:
        VECTORS.parent.mkdir(parents=True, exist_ok=True)
        VECTORS.write_text(json.dumps(actual, indent=2) + "\n")
        print(f"wrote {VECTORS}")
        return 0
    if args.check:
        if not VECTORS.exists():
            print(f"missing {VECTORS}")
            return 1
        expected = json.loads(VECTORS.read_text())
        if expected != actual:
            for key in ("zone", "feed", "pool", "book", "terms"):
                if expected.get(key) != actual[key]:
                    print(f"MISMATCH {key}")
                    print(f"  expected {expected.get(key)}")
                    print(f"  actual   {actual[key]}")
            return 1
        print("market terms vectors: ok")
        return 0
    print(json.dumps(actual, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
