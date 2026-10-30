#!/usr/bin/env python3
"""Read-only identity and safety preflight for the public testnet.

Pins the network id, shard and genesis block; checks the node accepts deploys
at our phlo price; checks the key file is fresh, 0600 and untracked; records the
node version, height, finality and CLI digest. Writes no chain state.

Exit codes: 0 ok, 2 identity mismatch, 3 unsafe keys, 4 node unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import requests  # noqa: E402

import netconfig  # noqa: E402

DEVNET_DEPLOYER_SECRET = "a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76"
LIVE_HINTS = ("rhobot.net", "164.90.140.144", "167.99.43.214")


class PreflightError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def get(base: str, path: str):
    response = requests.get(f"{base.rstrip('/')}{path}", timeout=netconfig.READ_TIMEOUT)
    if response.status_code >= 400:
        raise PreflightError(4, f"GET {path} -> {response.status_code}: {response.text[:300]}")
    return response.json()


def genesis(base: str) -> dict:
    value = get(base, "/api/blocks/0/0")
    if isinstance(value, list):
        if not value:
            raise PreflightError(2, "genesis block list is empty")
        return value[0]
    if isinstance(value, dict):
        return value
    raise PreflightError(2, f"genesis block shape: {type(value).__name__}")


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def check_keys(keys_path: Path) -> dict:
    if not keys_path.is_file():
        raise PreflightError(3, f"keys file missing: {keys_path}")
    mode = keys_path.stat().st_mode & 0o777
    if mode != 0o600:
        raise PreflightError(3, f"keys file mode {oct(mode)} is not 0600")
    ignored = git("check-ignore", str(keys_path))
    if not ignored:
        raise PreflightError(3, f"keys file is not gitignored: {keys_path}")
    tracked = git("ls-files", str(keys_path))
    if tracked:
        raise PreflightError(3, f"keys file is tracked by git: {keys_path}")
    keys = json.loads(keys_path.read_text())
    if "deployer" not in keys:
        raise PreflightError(3, "keys file has no deployer")
    for name, entry in keys.items():
        if entry.get("secret") == DEVNET_DEPLOYER_SECRET:
            raise PreflightError(3, f"key {name} is the public devnet deployer")
    devnet = ROOT / ".devnet" / "keys.json"
    if devnet.is_file() and keys_path.resolve() != devnet.resolve():
        devnet_pubs = {e.get("public") for e in json.loads(devnet.read_text()).values()}
        shared = [name for name, entry in keys.items() if entry.get("public") in devnet_pubs]
        if shared:
            raise PreflightError(3, f"testnet keys reuse devnet identities: {shared}")
    return keys


def check_cli() -> dict:
    binary = netconfig.CLI_BINARY
    if not binary.is_file():
        return {"path": str(binary), "present": False}
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    version = subprocess.run([str(binary), "--version"], capture_output=True,
                             text=True, timeout=30)
    return {"path": str(binary), "present": True, "sha256": digest,
            "version": (version.stdout or version.stderr).strip()}


def preflight(node: str, allow_live: bool, keys_path: Path | None = None) -> dict:
    if any(hint in node for hint in LIVE_HINTS) and not allow_live:
        raise PreflightError(2, "live endpoint requires --allow-live")
    profile = netconfig.profile()
    status = get(node, "/api/v1/status")
    try:
        health = get(node, "/health")
    except PreflightError:
        https = profile.get("https")
        if not https:
            raise
        health = get(https, "/health")
    block0 = genesis(node)
    last = get(node, "/api/last-finalized-block").get("blockInfo", {})
    latest = int(status.get("latestBlockNumber", -1))
    if status.get("networkId") != profile.get("networkId"):
        raise PreflightError(2, f"networkId {status.get('networkId')} != {profile.get('networkId')}")
    if status.get("shardId") != profile.get("shardId"):
        raise PreflightError(2, f"shardId {status.get('shardId')} != {profile.get('shardId')}")
    if block0.get("blockHash") != profile.get("genesisBlockHash"):
        raise PreflightError(
            2, f"genesis {block0.get('blockHash')} != {profile.get('genesisBlockHash')}")
    if block0.get("shardId") != profile.get("shardId"):
        raise PreflightError(2, f"genesis shard {block0.get('shardId')}")
    if block0.get("blockNumber") != 0:
        raise PreflightError(2, f"genesis block number {block0.get('blockNumber')}")
    if not status.get("acceptsDeploys"):
        raise PreflightError(4, "node does not accept deploys")
    if status.get("degraded") not in (None, "normal"):
        raise PreflightError(4, f"node degraded: {status.get('degraded')}")
    if int(status.get("minPhloPrice", 1)) > netconfig.PHLO_PRICE:
        raise PreflightError(4, "phlo price below minPhloPrice")
    if latest <= 0:
        raise PreflightError(4, "node has no tip")
    if int(last.get("blockNumber", -1)) > latest:
        raise PreflightError(2, "finalized block ahead of tip")
    if not health.get("ok"):
        raise PreflightError(4, "health not ok")
    if not health.get("finalized_fringe"):
        raise PreflightError(4, "finalized fringe unavailable")
    if int(health.get("mem_available_mb", 0)) < 512:
        raise PreflightError(4, "node memory below 512 MiB")
    resolved_keys = keys_path or netconfig.KEYS_PATH
    if resolved_keys.is_file():
        keys = check_keys(resolved_keys)
        key_info = {
            "path": str(resolved_keys), "present": True,
            "count": len(keys), "deployer_address": keys["deployer"]["address"],
        }
    else:
        key_info = {"path": str(resolved_keys), "present": False, "count": 0}
    result = {
        "ok": True,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "node": node,
        "node_version": (status.get("version") or {}).get("node"),
        "networkId": status.get("networkId"),
        "shardId": status.get("shardId"),
        "genesis": block0.get("blockHash"),
        "height": latest,
        "finalized": last.get("blockHash"),
        "finalizedHeight": last.get("blockNumber"),
        "peers": status.get("peers"),
        "nodes": status.get("nodes"),
        "minPhloPrice": status.get("minPhloPrice"),
        "autopropose": status.get("autopropose"),
        "proposeOnDeploy": status.get("proposeOnDeploy"),
        "devMode": status.get("devMode"),
        "acceptsDeploys": status.get("acceptsDeploys"),
        "mem_available_mb": health.get("mem_available_mb"),
        "keys": key_info,
        "cli": check_cli(),
        "source_sha": git("rev-parse", "HEAD"),
        "profile": str(netconfig.PROFILE_PATH),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", default=netconfig.NODE_URL)
    ap.add_argument("--keys", type=Path, default=netconfig.KEYS_PATH)
    ap.add_argument("--out", type=Path, default=netconfig.PREFLIGHT_PATH)
    ap.add_argument("--allow-live", action="store_true")
    args = ap.parse_args(argv)
    try:
        result = preflight(args.node, args.allow_live, args.keys)
    except PreflightError as error:
        print(f"preflight REFUSED: {error}", file=sys.stderr)
        return error.code
    except requests.RequestException as error:
        print(f"preflight unavailable: {error}", file=sys.stderr)
        return 4
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in (
        "networkId", "shardId", "genesis", "height", "node_version",
        "acceptsDeploys", "minPhloPrice")}, indent=2))
    print(f"preflight: ok -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
