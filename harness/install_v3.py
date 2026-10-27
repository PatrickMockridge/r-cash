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


def root_resolve_many(root_uri: str, block_hash: str, keys: list[str]) -> list[str]:
    """Resolve several Root keys at a pinned block. A missing key yields ``missing``."""
    channels = ", ".join(f"c{i}" for i in range(len(keys)))
    outs = ", ".join(f"o{i}" for i in range(len(keys)))
    sends = " | ".join(
        f'Root!("resolve", "{key}", 1, *c{i})' for i, key in enumerate(keys)
    )
    arms = " | ".join(
        f'for (@a{i} <- c{i}) {{ match a{i} {{ (true, u, _) => o{i}!(u)\n _ => o{i}!("missing") }} }}'
        for i in range(len(keys))
    )
    joins = "; ".join(f"@u{i} <- o{i}" for i in range(len(keys)))
    values = ", ".join(f"u{i}" for i in range(len(keys)))
    term = (
        f"new rl(`rho:registry:lookup`), rCh, Root, out, {channels}, {outs} in {{"
        f' rl!(`{root_uri}`, *rCh) | for (Root <- rCh) {{ {sends} | {arms} |'
        f" for ({joins}) {{ out!([{values}]) }} }} }}"
    )
    doc = node.explore_at(term, block_hash)
    return walk(doc.get("expr"), [])


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
    from install_testnet import STEP_KEYS

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

    def step(name: str, key: str, replacements: dict[str, str],
             expected: list[str]) -> dict:
        steps = state.setdefault("steps", {})
        if key in steps and steps[key].get("uris"):
            print(f"{name}: already installed")
            return steps[key]
        result = deploy_step(name, replacements, secret)
        block_hash = result.get("block_hash")
        if block_hash and state.get("root_uri"):
            resolved = root_resolve_many(state["root_uri"], block_hash, expected)
            if "missing" in resolved:
                raise SystemExit(
                    f"REFUSED step={name} detail=Root keys {expected} missing at {block_hash}"
                )
            result["uris"] = resolved + [
                uri for uri in result["uris"] if uri not in resolved
            ]
        steps[key] = result
        save(state)
        return result

    root = step("00_root", "root", {
        "__INSTALLER_PUB__": installer,
        "__ADMIN_KEYS__": admins,
    }, [])
    root_uri = root["uris"][0]
    state["root_uri"] = root_uri
    save(state)
    if root.get("block_hash"):
        root_keys = root_resolve_many(root_uri, root["block_hash"], ["rcash:root"])
        if "missing" in root_keys:
            raise SystemExit(f"REFUSED step=root detail=rcash:root missing at {root['block_hash']}")

    common = {"__ROOT_URI__": root_uri}
    admin = step("03_admin_guard", "admin_guard", common, STEP_KEYS["admin_guard"])
    state["admin_guard_uri"] = admin["uris"][0]
    save(state)

    kernel = step("01_kernel", "kernel", common, STEP_KEYS["kernel"])
    state["clock_uri"] = kernel["uris"][0]
    state["verifier_uri"] = kernel["uris"][1]
    state["codec_uri"] = kernel["uris"][2]
    save(state)

    bounds = step("02_bounds", "bounds", common, STEP_KEYS["bounds"])
    state["bounds_uri"] = bounds["uris"][0]
    save(state)

    governor = step("04_governor", "governor", {
        "__ROOT_URI__": root_uri,
        "__ADMIN_KEYS__": admins,
    }, STEP_KEYS["governor"])
    state["governor_uri"] = governor["uris"][0]
    save(state)

    for name in ["05_amm_math", "06_collateral_math", "07_oracle_math", "08_claim_code"]:
        result = step(name, name, common, STEP_KEYS[name])
        state[f"{name}_uri"] = result["uris"][0]
        save(state)

    allowlist = "[" + ", ".join(
        f'"{keys[n]["public"]}"' for n in ["reporter1", "reporter2", "reporter3"]
    ) + "]"
    registry = step("12_oracle_registry", "oracle_registry", {
        "__ROOT_URI__": root_uri,
        "__ADMIN_KEYS__": admins,
        "__ALLOWLIST__": allowlist,
    }, STEP_KEYS["oracle_registry"])
    state["oracle_registry_uri"] = registry["uris"][0]
    save(state)

    hub = step("13_oracle_hub", "oracle_hub", common, STEP_KEYS["oracle_hub"])
    state["oracle_hub_uri"] = hub["uris"][0]
    save(state)

    currencies = step("32_currency_registry", "currency_registry", common, STEP_KEYS["currency_registry"])
    state["stablecoin_directory_uri"] = currencies["uris"][0]
    state["currency_registry_uri"] = currencies["uris"][1]
    save(state)

    resolver = step("14_asset_resolver", "asset_resolver", common, STEP_KEYS["asset_resolver"])
    state["asset_resolver_uri"] = resolver["uris"][0]
    save(state)

    transfer = step("40_transfer", "transfer", {
        **common, "__BOOK_PARAMS__": '{"minAmount": 1, "defaultExpiryBlocks": 720, "maxExpiryBlocks": 1296000, "maxMemoBytes": 128, "maxOpIdBytes": 64, "maxStipend": 100000000}'}, STEP_KEYS["transfer"])
    state["transfer_book_uri"] = transfer["uris"][0]
    save(state)

    pool_template = step("51_pool", "pool_template", {
        "__ROOT_URI__": root_uri,
        "__ASSET_RESOLVER_URI__": resolver["uris"][0],
    }, STEP_KEYS["pool_template"])
    state["pool_template_uri"] = pool_template["uris"][0]
    save(state)

    market = step("50_market", "market", {
        "__ROOT_URI__": root_uri,
        "__ASSET_RESOLVER_URI__": resolver["uris"][0],
        "__MIN_LOCK_BLOCKS__": "10",
    }, STEP_KEYS["market"])
    state["market_terms_uri"] = market["uris"][0]
    state["market_directory_uri"] = market["uris"][1]
    state["market_index_uri"] = market["uris"][2]
    state["market_factory_uri"] = market["uris"][3]
    state["tradability_gate_uri"] = market["uris"][4]
    state["listing_views_uri"] = market["uris"][5]
    save(state)

    identity = step("09_identity", "identity", {
        "__ROOT_URI__": root_uri,
        "__ASSET_RESOLVER_URI__": resolver["uris"][0],
    }, STEP_KEYS["identity"])
    state["account_factory_uri"] = identity["uris"][0]
    save(state)

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
    out = ROOT / "deployments" / "devnet-v4.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest: {out.relative_to(ROOT)}")
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
