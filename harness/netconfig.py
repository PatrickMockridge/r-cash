"""One source of network, path and deploy settings for the harness.

The devnet suites were written against `.devnet/`, localhost and the docker
backend. Public-testnet runs need the same suites with different paths, shard,
phlo and transport. Set `RCASH_NET=testnet` and everything below follows the
testnet profile; explicit `RCASH_*` variables override individual values.

This module only reads configuration. It never creates keys or touches a node.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "configs" / "testnet.json"


def net() -> str:
    return os.environ.get("RCASH_NET", "devnet").strip().lower()


def is_testnet() -> bool:
    return net() == "testnet"


def profile() -> dict:
    if not is_testnet():
        return {}
    return json.loads(PROFILE_PATH.read_text())


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw) if raw else default


NODE_URL = os.environ.get(
    "RCASH_NODE",
    (profile().get("http") if is_testnet() else "http://localhost:40403"),
)
SHARD_ID = os.environ.get(
    "RCASH_SHARD",
    (profile().get("shardId") if is_testnet() else "/root"),
)
KEYS_PATH = _env_path(
    "RCASH_KEYS",
    ROOT / (".testnet/keys.json" if is_testnet() else ".devnet/keys.json"),
)
STATE_PATH = _env_path(
    "RCASH_STATE",
    ROOT / (".testnet/install.json" if is_testnet() else ".devnet/v3-install.json"),
)
OPS_PATH = _env_path(
    "RCASH_OPS",
    ROOT / (".testnet/ops" if is_testnet() else ".devnet/ops"),
)
MESH_STATE_PATH = _env_path(
    "RCASH_MESH_STATE",
    ROOT / (".testnet/mesh-state.json" if is_testnet() else ".devnet/mesh-state.json"),
)
MANIFEST_PATH = _env_path(
    "RCASH_MANIFEST",
    ROOT / (".testnet/testnet-v4.json" if is_testnet() else "deployments/devnet-v4.json"),
)
PREFLIGHT_PATH = ROOT / ".testnet" / "preflight.json"
FUNDING_PATH = ROOT / ".testnet" / "funding.json"
CLI_BINARY = ROOT / "target" / "debug" / "rcash"

_PROFILE = profile()
PHLO_LIMIT = int(os.environ.get("RCASH_PHLO_LIMIT", _PROFILE.get("phloLimit", 2_000_000)))
PHLO_PRICE = int(os.environ.get("RCASH_PHLO_PRICE", _PROFILE.get("phloPrice", 1)))
TICKER_PHLO_LIMIT = int(_PROFILE.get("tickerPhloLimit", 200_000))
TICKER_INTERVAL = float(os.environ.get(
    "RCASH_TICKER_INTERVAL", _PROFILE.get("tickerIntervalSeconds", 2.0)))
DEPLOY_TIMEOUT = float(os.environ.get(
    "RCASH_DEPLOY_TIMEOUT", _PROFILE.get("deployTimeoutSeconds", 600)))
FINALITY_TIMEOUT = float(os.environ.get(
    "RCASH_FINALITY_TIMEOUT", _PROFILE.get("finalityTimeoutSeconds", 600)))
READ_TIMEOUT = float(os.environ.get("RCASH_READ_TIMEOUT",
                                    _PROFILE.get("readTimeoutSeconds", 30)))


def remote() -> bool:
    """True when deploys must go through the Rust CLI rather than docker exec."""
    return is_testnet() or os.environ.get("RCASH_REMOTE") == "1"


def live_endpoints() -> list[str]:
    entries = [NODE_URL]
    if is_testnet():
        entries += _PROFILE.get("httpFallbacks", [])
        entries += [_PROFILE.get("https", "")]
    return [entry for entry in entries if entry]


def pool_argument(base: str | None = None) -> list[str]:
    """The CLI's known-node argument (`--nodes`), or [] when there is only one.

    Deploys go through the Rust CLI, which discovers the hostlist in the background.
    Until the public testnet binary publishes one, this list is how the harness still
    spreads work over the validators named in the profile.
    """
    entries = [base or NODE_URL, *live_endpoints()]
    ordered: list[str] = []
    for entry in entries:
        # The native CLI has no TLS backend; the HTTPS endpoint is for the browser.
        if entry and entry.startswith("http://") and entry not in ordered:
            ordered.append(entry)
    return ["--nodes", ",".join(ordered)] if len(ordered) > 1 else []


def load_keys() -> dict:
    return json.loads(KEYS_PATH.read_text())


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text())


def key_name_for_secret(secret_hex: str) -> str:
    for name, entry in load_keys().items():
        if entry.get("secret") == secret_hex:
            return name
    raise RuntimeError("deploy secret is not present in the active keys file")
