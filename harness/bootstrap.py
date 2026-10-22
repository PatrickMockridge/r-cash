#!/usr/bin/env python3
"""Render and deploy the bootstrap term, then write deployments/devnet.json.

The oracle and admin public keys come from .devnet/keys.json (make keys).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import deploy as node  # noqa: E402
from minify_rho import minify  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
BUILT = ROOT / "contracts" / "build" / "deploy" / "00_bootstrap.rho"
MANIFEST = ROOT / "deployments" / "devnet.json"


def key_list(keys: dict, names: list[str]) -> str:
    return "[" + ", ".join(f'"{keys[n]["public"]}".hexToBytes()' for n in names) + "]"


def walk(value, out):
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("ExprUri", "ExprString") and isinstance(v, dict):
                out.append(v.get("data"))
            else:
                walk(v, out)
    elif isinstance(value, list):
        for v in value:
            walk(v, out)
    return out


def main() -> int:
    keys = json.loads(KEYS.read_text())
    term = BUILT.read_text()
    term = term.replace("__REPORTER_KEYS__", key_list(keys, ["reporter1", "reporter2", "reporter3"]))
    term = term.replace("__ADMIN_KEYS__", key_list(keys, ["admin1", "admin2", "admin3"]))
    term = term.replace("__ZONE_PARAMS__", "[20000, 800, 5000, 3171, 10000000000000, 1000000, 10000000000000]")
    term = term.replace("__POOL_PARAMS__", "[20, 80, 500]")
    if "__REPORTER_KEYS__" in term or "__ADMIN_KEYS__" in term or "__ZONE_PARAMS__" in term or "__POOL_PARAMS__" in term:
        print("unresolved bootstrap placeholders", file=sys.stderr)
        return 1

    term = minify(term)
    print(f"bootstrap term: {len(term.encode())} bytes")
    did = node.deploy(term, keys["deployer"]["secret"], phlo_limit=100_000_000)
    print("deploy", did)
    variant, payload = node.wait_processed(did, timeout=180)
    if variant != "processedwithsuccess":
        print(f"bootstrap failed: {variant} {json.dumps(payload)[:2000]}", file=sys.stderr)
        return 1
    uris = [u for u in walk(payload.get("deployResult"), [])
            if isinstance(u, str) and u.startswith("rho:id:")]
    if len(uris) < 6:
        print(f"expected 6 component URIs, got {uris}", file=sys.stderr)
        return 1
    block = payload.get("block") or {}
    manifest = {
        "directory_uri": uris[0],
        "account_factory_uri": uris[1],
        "oracle_uri": uris[2],
        "zone_ngn_uri": uris[3],
        "zone_kes_uri": uris[4],
        "components_uri": uris[5],
        "block_hash": block.get("blockHash"),
        "block_number": block.get("blockNumber"),
        "deploy_id": did,
        "node_commit": "e2d073dcd02f1e560ccb84749937138a1e184b0b",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
