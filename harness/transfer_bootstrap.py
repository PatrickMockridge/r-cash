#!/usr/bin/env python3
"""Deploy the TransferBook into Components."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import deploy as node  # noqa: E402
from minify_rho import minify  # noqa: E402
MANIFEST = ROOT / "deployments" / "devnet.json"; KEYS = ROOT / ".devnet" / "keys.json"
BUILD = ROOT / "contracts" / "build" / "deploy"
def main() -> int:
    m = json.loads(MANIFEST.read_text()); keys = json.loads(KEYS.read_text())
    t = (BUILD / "13_transfer.rho").read_text()
    t = t.replace("__DIRECTORY_URI__", m["directory_uri"]).replace("__COMPONENTS_URI__", m["components_uri"])
    print("transfer bytes", len(minify(t).encode()))
    did = node.deploy(minify(t), keys["deployer"]["secret"], phlo_limit=80_000_000)
    variant, payload = node.wait_processed(did, timeout=240)
    print("transfer", did, variant, json.dumps(payload.get("deployResult"))[:400])
    if variant != "processedwithsuccess": return 1
    m["transfer_installed"] = True
    m["transfer_installed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
