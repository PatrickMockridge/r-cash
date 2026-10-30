#!/usr/bin/env python3
"""Generate a fresh, testnet-only key file.

Uses the Rust CLI's random keygen (never the baked devnet deployer), writes
mode 0600 under `.testnet/`, and refuses to proceed if the file is tracked or
reuses a devnet identity.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import netconfig  # noqa: E402
from testnet_preflight import DEVNET_DEPLOYER_SECRET  # noqa: E402

NAMES = [
    "deployer",
    "admin1", "admin2", "admin3",
    "reporter1", "reporter2", "reporter3",
    "sponsor", "sender", "business", "recipient", "ramp",
    *[f"key{i}" for i in range(12, 22)],
    *[f"bank{i}" for i in range(1, 141)],
    "filler1", "filler2", "filler3",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=netconfig.KEYS_PATH)
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args(argv)
    out = args.out
    if args.fresh and out.exists():
        out.unlink()
    if out.exists():
        raise SystemExit(f"{out} exists; pass --fresh to rotate it")
    if not str(out).startswith(str(ROOT / ".testnet")):
        raise SystemExit("testnet keys must live under .testnet/")
    if not netconfig.CLI_BINARY.is_file():
        raise SystemExit(f"missing {netconfig.CLI_BINARY}; run cargo build -p rcash-cli")
    proc = subprocess.run(
        [str(netconfig.CLI_BINARY), "keygen", "--out", str(out),
         "--names", ",".join(NAMES)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise SystemExit(f"keygen failed: {proc.stderr or proc.stdout}")
    mode = out.stat().st_mode & 0o777
    if mode != 0o600:
        raise SystemExit(f"keygen wrote mode {oct(mode)}, expected 0600")
    keys = json.loads(out.read_text())
    for entry in keys.values():
        if entry.get("secret") == DEVNET_DEPLOYER_SECRET:
            out.unlink()
            raise SystemExit("generated key matches the public devnet deployer")
    print(f"wrote {out} ({len(keys)} keys, mode 0600)")
    for name, entry in keys.items():
        print(f"  {name:12s} {entry['address']}  {entry['public'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
