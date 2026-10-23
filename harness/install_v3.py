#!/usr/bin/env python3
"""Install the v0.3 kernel and platform components on a fresh devnet.

This is deliberately small for Phase 2: Root, AdminGuard, Clock, Verifier,
Codec, Bounds, the pure math components and Governor. Later phases add the
registries, zones, feeds, markets and accounts.

Usage:
    python3 harness/install_v3.py [--fresh]

The installer is idempotent on .devnet/v3-install.json. `--fresh` ignores and
replaces that state; it does not reset the chain (use `make down && make devnet`
for a genesis install).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import deploy as node  # noqa: E402
from minify_rho import minify  # noqa: E402

BUILD = ROOT / "contracts" / "build" / "deploy" / "v3"
KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"
PHLO = 100_000_000
PLACEHOLDER = re.compile(r"__[A-Z0-9_]+__")


def render(name: str, replacements: dict[str, str]) -> str:
    path = BUILD / f"{name}.rho"
    if not path.is_file():
        raise SystemExit(f"missing built term {path}; run tools/build_contracts.py")
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(key, value)
    leftover = PLACEHOLDER.findall(text)
    if leftover:
        raise SystemExit(f"{name}: unresolved placeholders {sorted(set(leftover))}")
    text = minify(text)
    size = len(text.encode("utf-8"))
    if size > 65_536:
        raise SystemExit(f"{name}: {size} bytes exceeds the 65,536-byte term limit")
    print(f"{name}: {size} bytes")
    return text


def walk(value, out: list[str]) -> list[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("ExprUri", "ExprString") and isinstance(item, dict):
                out.append(item.get("data"))
            else:
                walk(item, out)
    elif isinstance(value, list):
        for item in value:
            walk(item, out)
    return out


def deploy_step(name: str, replacements: dict[str, str], secret: str) -> dict:
    term = render(name, replacements)
    deploy_id = node.deploy(term, secret, phlo_limit=PHLO)
    print(f"{name}: deploy {deploy_id}")
    variant, payload = node.wait_processed(deploy_id, timeout=300)
    if variant != "processedwithsuccess":
        raise SystemExit(f"{name}: {variant} {json.dumps(payload)[:3000]}")
    uris = [
        uri
        for uri in walk(payload.get("deployResult"), [])
        if isinstance(uri, str) and uri.startswith("rho:id:")
    ]
    block = payload.get("block") or {}
    block_hash = block.get("blockHash")
    if block_hash:
        node.wait_finalized(block_hash)
    return {
        "deploy_id": deploy_id,
        "uris": uris,
        "block_hash": block_hash,
        "block_number": block.get("blockNumber"),
    }


def key_list(keys: dict, names: list[str]) -> str:
    return "[" + ", ".join(f'"{keys[n]["public"]}".hexToBytes()' for n in names) + "]"


def save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="ignore and replace the local install state")
    args = ap.parse_args(argv)

    if not KEYS.is_file():
        raise SystemExit(f"missing {KEYS}; run make keys")
    keys = json.loads(KEYS.read_text())
    secret = keys["deployer"]["secret"]
    installer = keys["deployer"]["public"]
    admins = key_list(keys, ["admin1", "admin2", "admin3"])

    if STATE.is_file() and not args.fresh:
        state = json.loads(STATE.read_text())
    else:
        state = {}
    if args.fresh:
        STATE.unlink(missing_ok=True)

    def step(name: str, key: str, replacements: dict[str, str]) -> dict:
        steps = state.setdefault("steps", {})
        if key in steps and steps[key].get("uris"):
            print(f"{name}: already installed")
            return steps[key]
        result = deploy_step(name, replacements, secret)
        steps[key] = result
        save(state)
        return result

    root = step("00_root", "root", {
        "__INSTALLER_PUB__": installer,
        "__ADMIN_KEYS__": admins,
    })
    root_uri = root["uris"][0]
    state["root_uri"] = root_uri
    save(state)

    common = {"__ROOT_URI__": root_uri}
    admin = step("03_admin_guard", "admin_guard", common)
    state["admin_guard_uri"] = admin["uris"][0]
    save(state)

    kernel = step("01_kernel", "kernel", common)
    state["clock_uri"] = kernel["uris"][0]
    state["verifier_uri"] = kernel["uris"][1]
    state["codec_uri"] = kernel["uris"][2]
    save(state)

    bounds = step("02_bounds", "bounds", common)
    state["bounds_uri"] = bounds["uris"][0]
    save(state)

    governor = step("04_governor", "governor", {
        "__ROOT_URI__": root_uri,
        "__ADMIN_KEYS__": admins,
    })
    state["governor_uri"] = governor["uris"][0]
    save(state)

    for name in ["05_amm_math", "06_risk_math", "07_oracle_math", "08_claim_code"]:
        result = step(name, name, common)
        state[f"{name}_uri"] = result["uris"][0]
        save(state)

    identity = step("09_identity", "identity", common)
    state["account_factory_uri"] = identity["uris"][0]
    save(state)

    allowlist = "[" + ", ".join(
        f'"{keys[n]["public"]}"' for n in ["reporter1", "reporter2", "reporter3"]
    ) + "]"
    registry = step("12_oracle_registry", "oracle_registry", {
        "__ROOT_URI__": root_uri,
        "__ADMIN_KEYS__": admins,
        "__ALLOWLIST__": allowlist,
    })
    state["oracle_registry_uri"] = registry["uris"][0]
    save(state)

    hub = step("13_oracle_hub", "oracle_hub", common)
    state["oracle_hub_uri"] = hub["uris"][0]
    save(state)

    template = step("30_zone_template", "zone_template", common)
    state["zone_template_uri"] = template["uris"][0]
    save(state)

    zone_factory = step("10_zone_factory", "zone_factory", common)
    state["zone_directory_uri"] = zone_factory["uris"][0]
    state["zone_factory_uri"] = zone_factory["uris"][1]
    save(state)

    currency_registry = step("11_currency_registry", "currency_registry", {
        "__ROOT_URI__": root_uri,
        "__ADMIN_KEYS__": admins,
    })
    state["currency_registry_uri"] = currency_registry["uris"][0]
    save(state)

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
