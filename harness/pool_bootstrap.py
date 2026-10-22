#!/usr/bin/env python3
"""Create the rNGN/rKES FxPool in two deploys (setup + pool) against the 3.5 bootstrap."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import deploy as node  # noqa: E402
from minify_rho import minify  # noqa: E402

MANIFEST = ROOT / "deployments" / "devnet.json"
KEYS = ROOT / ".devnet" / "keys.json"
BUILD = ROOT / "contracts" / "build" / "deploy"

def deploy_term(term: str, phlo: int):
    keys = json.loads(KEYS.read_text())
    did = node.deploy(minify(term), keys["deployer"]["secret"], phlo_limit=phlo)
    variant, payload = node.wait_processed(did, timeout=240)
    return did, variant, payload

def main() -> int:
    m = json.loads(MANIFEST.read_text()); keys = json.loads(KEYS.read_text())
    admins = "[" + ", ".join(f'"{keys[n]["public"]}".hexToBytes()' for n in ["admin1","admin2","admin3"]) + "]"
    setup = (BUILD / "10_pool_setup.rho").read_text()
    setup = setup.replace("__DIRECTORY_URI__", m["directory_uri"]).replace("__COMPONENTS_URI__", m["components_uri"])
    print("setup bytes", len(minify(setup).encode()))
    did, variant, payload = deploy_term(setup, 40_000_000)
    print("setup", did, variant, json.dumps(payload.get("deployResult"))[:400])
    if variant != "processedwithsuccess":
        return 1
    pool = (BUILD / "11_pool.rho").read_text()
    pool = pool.replace("__DIRECTORY_URI__", m["directory_uri"]).replace("__COMPONENTS_URI__", m["components_uri"])
    pool = pool.replace("__ADMIN_KEYS__", admins).replace("__POOL_PARAMS__", "[20, 80, 500]")
    print("pool bytes", len(minify(pool).encode()))
    did, variant, payload = deploy_term(pool, 80_000_000)
    print("pool", did, variant, json.dumps(payload.get("deployResult"))[:400])
    if variant != "processedwithsuccess":
        return 1
    m["pool_installed"] = True
    m["pool_installed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
