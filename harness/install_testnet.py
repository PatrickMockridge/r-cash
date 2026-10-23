#!/usr/bin/env python3
"""Install the v0.4 platform on the rhobot public testnet.

Deploys go through the Rust CLI (`rcash deploy`) against the testnet HTTP API, so the
same signed-deploy path the wallet uses is the one the installer exercises. State is
local (`.testnet/install.json`); `--fresh` ignores it but does not reset the chain.

Usage:
    python3 harness/install_testnet.py [--fresh] [--node URL]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "contracts" / "build" / "deploy" / "v3"
KEYS = ROOT / ".testnet" / "keys.json"
DEVNET_KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".testnet" / "install.json"
RCASH = ROOT / "target" / "debug" / "rcash"
NODE = "http://164.90.140.144:40403"
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
    size = len(text.encode("utf-8"))
    print(f"{name}: {size} bytes")
    return text


def deploy(term: str, key: str = "deployer") -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".rho", delete=False) as handle:
        handle.write(term)
        path = handle.name
    try:
        proc = subprocess.run(
            [str(RCASH), "--node", NODE, "--keys", str(KEYS), "--key", key,
             "--json", "deploy", path],
            capture_output=True, text=True, timeout=600,
        )
    finally:
        Path(path).unlink(missing_ok=True)
    out = (proc.stdout or "").strip().splitlines()
    doc = None
    for line in reversed(out):
        line = line.strip()
        if line.startswith("{"):
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            break
    if doc is None:
        clean = ((proc.stdout or "") + (proc.stderr or "")).split("___ Begin jemalloc")[0]
        raise SystemExit(f"deploy produced no JSON (rc={proc.returncode}):\n{clean[:2000]}")
    if doc.get("error"):
        raise SystemExit(f"deploy failed: {doc['error']}")
    if "success" not in str(doc.get("status", "")).lower():
        raise SystemExit(f"deploy not successful: {doc}")
    return doc


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


def uris(doc: dict) -> list[str]:
    return [
        uri
        for uri in walk(doc.get("result"), [])
        if isinstance(uri, str) and uri.startswith("rho:id:")
    ]


def key_list(keys: dict, names: list[str]) -> str:
    return "[" + ", ".join(f'"{keys[n]["public"]}".hexToBytes()' for n in names) + "]"


def save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    global NODE
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--node", default=NODE)
    args = ap.parse_args(argv)
    NODE = args.node

    keys = json.loads(KEYS.read_text())
    deployer = keys["deployer"]
    devnet = json.loads(DEVNET_KEYS.read_text())
    admins = key_list(devnet, ["admin1", "admin2", "admin3"])

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
        doc = deploy(render(name, replacements), "deployer")
        found = uris(doc)
        steps[key] = {"deploy_id": doc.get("deployId"), "uris": found,
                      "block": doc.get("blockHash")}
        save(state)
        print(f"{name}: {found}")
        return steps[key]

    root = step("00_root", "root", {
        "__INSTALLER_PUB__": deployer["public"],
        "__ADMIN_KEYS__": admins,
    })
    root_uri = root["uris"][0]
    state["root_uri"] = root_uri
    save(state)

    common = {"__ROOT_URI__": root_uri}
    admin = step("03_admin_guard", "admin_guard", common)
    state["admin_guard_uri"] = admin["uris"][0]

    kernel = step("01_kernel", "kernel", common)
    state["clock_uri"], state["verifier_uri"], state["codec_uri"] = kernel["uris"][:3]

    bounds = step("02_bounds", "bounds", common)
    state["bounds_uri"] = bounds["uris"][0]

    governor = step("04_governor", "governor", {
        "__ROOT_URI__": root_uri,
        "__ADMIN_KEYS__": admins,
    })
    state["governor_uri"] = governor["uris"][0]

    for name in ["05_amm_math", "06_collateral_math", "07_oracle_math", "08_claim_code"]:
        result = step(name, name, common)
        state[f"{name}_uri"] = result["uris"][0]

    allowlist = "[" + ", ".join(
        f'"{devnet[n]["public"]}"' for n in ["reporter1", "reporter2", "reporter3"]
    ) + "]"
    registry = step("12_oracle_registry", "oracle_registry", {
        "__ROOT_URI__": root_uri,
        "__ADMIN_KEYS__": admins,
        "__ALLOWLIST__": allowlist,
    })
    state["oracle_registry_uri"] = registry["uris"][0]

    hub = step("13_oracle_hub", "oracle_hub", common)
    state["oracle_hub_uri"] = hub["uris"][0]

    currencies = step("32_currency_registry", "currency_registry", common)
    state["stablecoin_directory_uri"] = currencies["uris"][0]
    state["currency_registry_uri"] = currencies["uris"][1]

    resolver = step("14_asset_resolver", "asset_resolver", common)
    state["asset_resolver_uri"] = resolver["uris"][0]

    transfer = step("40_transfer", "transfer", common)
    state["transfer_book_uri"] = transfer["uris"][0]

    pool = step("51_pool", "pool_template", {
        "__ROOT_URI__": root_uri,
        "__ASSET_RESOLVER_URI__": resolver["uris"][0],
    })
    state["pool_template_uri"] = pool["uris"][0]

    market = step("50_market", "market", {
        "__ROOT_URI__": root_uri,
        "__ASSET_RESOLVER_URI__": resolver["uris"][0],
    })
    state["market_terms_uri"] = market["uris"][0]
    state["market_directory_uri"] = market["uris"][1]
    state["market_index_uri"] = market["uris"][2]
    state["market_factory_uri"] = market["uris"][3]
    state["tradability_gate_uri"] = market["uris"][4]
    state["listing_views_uri"] = market["uris"][5]

    identity = step("09_identity", "identity", {
        "__ROOT_URI__": root_uri,
        "__ASSET_RESOLVER_URI__": resolver["uris"][0],
    })
    state["account_factory_uri"] = identity["uris"][0]

    manifest = {
        "root_uri": state["root_uri"],
        "clock_uri": state["clock_uri"],
        "verifier_uri": state["verifier_uri"],
        "codec_uri": state["codec_uri"],
        "bounds_uri": state["bounds_uri"],
        "admin_guard_uri": state["admin_guard_uri"],
        "governor_uri": state["governor_uri"],
        "amm_math_uri": state["05_amm_math_uri"],
        "oracle_registry_uri": state["oracle_registry_uri"],
        "oracle_hub_uri": state["oracle_hub_uri"],
        "currency_registry_uri": state["currency_registry_uri"],
        "stablecoin_directory_uri": state["stablecoin_directory_uri"],
        "asset_resolver_uri": state["asset_resolver_uri"],
        "transfer_book_uri": state["transfer_book_uri"],
        "pool_template_uri": state["pool_template_uri"],
        "market_terms_uri": state["market_terms_uri"],
        "market_directory_uri": state["market_directory_uri"],
        "market_index_uri": state["market_index_uri"],
        "market_factory_uri": state["market_factory_uri"],
        "tradability_gate_uri": state["tradability_gate_uri"],
        "listing_views_uri": state["listing_views_uri"],
        "account_factory_uri": state["account_factory_uri"],
    }
    out = ROOT / "deployments" / "testnet-v4.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest: {out.relative_to(ROOT)}")
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
