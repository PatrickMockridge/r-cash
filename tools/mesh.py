#!/usr/bin/env python3
"""Plan and provision the R-Cash currency mesh.

    python3 tools/mesh.py plan [--config configs/mesh.json]
    python3 tools/mesh.py install [--config configs/mesh.json] [--pairs N]
    python3 tools/mesh.py pair BASE QUOTE

`plan` is pure and validates the tracked config. `install` runs on a
disposable devnet with the platform components already installed; it deploys
feeds and native systems, registers enabled external assets, then creates and
seeds the priority pairs. `pair` creates and seeds one non-priority pair.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

from mesh_support import (  # noqa: E402
    activate_market,
    create_market,
    deploy_and_register_issuer,
    ensure_feed,
    load_env,
    register_external,
    seed_market,
)

DEFAULT_CONFIG = ROOT / "configs" / "mesh.json"
STATE_OUT = ROOT / ".devnet" / "mesh-state.json"


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text())
    validate(config)
    return config


def enabled(config: dict) -> list[dict]:
    return config["currencies"] + [
        asset for asset in config["externalAssets"] if asset.get("enabled")
    ]


def validate(config: dict) -> None:
    codes = [currency["code"] for currency in enabled(config)]
    if len(codes) != len(set(codes)):
        raise SystemExit("mesh: duplicate currency code")
    for code in [config["defaultCurrency"], *config["majorCurrencies"]]:
        if code not in codes:
            raise SystemExit(f"mesh: {code} is not an enabled currency")
    seen = set()
    for pair in config["priorityPairs"]:
        base, quote = pair["base"], pair["quote"]
        if base == quote:
            raise SystemExit(f"mesh: {base}/{quote} is not a pair")
        if base not in codes or quote not in codes:
            raise SystemExit(f"mesh: {base}/{quote} uses an unknown currency")
        key = tuple(sorted((base, quote)))
        if key in seen:
            raise SystemExit(f"mesh: duplicate pair {base}/{quote}")
        seen.add(key)
    for asset in config["externalAssets"]:
        if asset.get("enabled") and not asset.get("adapterUri"):
            raise SystemExit(f"mesh: {asset['code']} is enabled without an adapterUri")


def cmd_plan(config: dict) -> int:
    native = config["currencies"]
    external = [a for a in config["externalAssets"] if a.get("enabled")]
    print(f"mesh {config['version']}: {len(native)} native, {len(external)} external, "
          f"{len(enabled(config))} assets")
    print(f"default {config['defaultCurrency']}; majors {', '.join(config['majorCurrencies'])}")
    print(f"native: {', '.join(c['code'] for c in native)}")
    if external:
        print(f"external: {', '.join(a['code'] for a in external)}")
    else:
        print("external: none enabled (adapterUri required)")
    print(f"priority pairs: {len(config['priorityPairs'])}")
    for pair in config["priorityPairs"]:
        print(f"  {pair['base']}/{pair['quote']}")
    total = len(enabled(config)) * (len(enabled(config)) - 1) // 2
    print(f"full mesh: {total} unordered pairs; the rest are permissionless")
    return 0


def install_asset(keys: dict, state: dict, config: dict, currency: dict) -> None:
    code = currency["code"]
    ensure_feed(keys, state, config, code, currency.get("initialPriceE8", 100_000_000))
    deploy_and_register_issuer(keys, state, config, code)
    print(f"native {code}: feed + system listed")


def cmd_install(config: dict, limit: int | None) -> int:
    keys, state = load_env()
    # REV is the collateral and the cross-rate anchor.
    ensure_feed(keys, state, config, "REV", config["currencies"][0]["initialPriceE8"] // 20 or 1)
    for currency in config["currencies"]:
        install_asset(keys, state, config, currency)
    for asset in config["externalAssets"]:
        if asset.get("enabled"):
            register_external(keys, state, config, asset["code"], asset["adapterUri"])
            print(f"external {asset['code']}: registered")
    pairs = config["priorityPairs"][:limit] if limit else config["priorityPairs"]
    results = []
    for pair in pairs:
        created = create_market(keys, state, config, pair["base"], pair["quote"])
        market = created["market"]
        if market.get("status") == "active":
            print(f"{pair['base']}/{pair['quote']}: already active")
            results.append({"base": pair["base"], "quote": pair["quote"],
                            "marketId": market.get("marketId"), "status": "active"})
            continue
        seed_market(keys, state, config, pair["base"], pair["quote"], created)
        status = activate_market(keys, state, market["marketId"])
        print(f"{pair['base']}/{pair['quote']}: seeded and {status}")
        results.append({"base": pair["base"], "quote": pair["quote"],
                        "marketId": market.get("marketId"), "status": status})
    STATE_OUT.write_text(json.dumps({"pairs": results}, indent=2) + "\n")
    print(f"wrote {STATE_OUT.relative_to(ROOT)}")
    return 0


def cmd_pair(config: dict, base: str, quote: str) -> int:
    keys, state = load_env()
    created = create_market(keys, state, config, base, quote)
    market = created["market"]
    if market.get("status") != "active":
        seed_market(keys, state, config, base, quote, created)
        status = activate_market(keys, state, market["marketId"])
        print(f"{base}/{quote}: seeded and {status}")
    else:
        print(f"{base}/{quote}: already active")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    install = sub.add_parser("install")
    install.add_argument("--pairs", type=int, default=None,
                         help="limit priority pairs (devnet smoke)")
    pair = sub.add_parser("pair")
    pair.add_argument("base")
    pair.add_argument("quote")
    args = ap.parse_args(argv)
    config = load_config(args.config)
    if args.command == "plan":
        return cmd_plan(config)
    if args.command == "install":
        return cmd_install(config, args.pairs)
    return cmd_pair(config, args.base.upper(), args.quote.upper())


if __name__ == "__main__":
    raise SystemExit(main())
