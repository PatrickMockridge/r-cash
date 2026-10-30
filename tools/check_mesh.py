#!/usr/bin/env python3
"""Static conformance checks for the tracked currency mesh.

This is the offline gate for the DEX configuration: the native set, the 120
unordered pairs, the majors/default, priority coverage and the external-asset
adapter rules. It never contacts a node.

    python3 tools/check_mesh.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "configs" / "mesh.json"
ACCEPTANCE = ROOT / "docs" / "spec" / "acceptance.yaml"

# The launch set in the approved plan. Changing it is a product decision and
# must update the plan, the acceptance entries and this set together.
LOCALS = {"NGN", "ZAR", "OMR", "AED", "EGP", "MAD", "ETB", "PKR", "INR",
          "BWP", "BRL", "CLP", "MXN"}
MAJORS = {"USD", "EUR", "CNY"}


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=CONFIG)
    args = ap.parse_args(argv)
    errors: list[str] = []
    config = json.loads(args.config.read_text())
    currencies = config.get("currencies") or []
    externals = config.get("externalAssets") or []
    codes = [entry.get("code") for entry in currencies]
    code_set = set(codes)

    if len(codes) != len(code_set):
        errors.append("duplicate native currency code")
    if len(codes) != 16:
        errors.append(f"native currency count {len(codes)} != 16")
    if set(config.get("majorCurrencies") or []) != MAJORS:
        errors.append("majorCurrencies must be USD, EUR, CNY")
    if config.get("defaultCurrency") != "USD":
        errors.append("defaultCurrency must be USD")
    if code_set != MAJORS | LOCALS:
        errors.append(f"native set mismatch: missing {sorted((MAJORS | LOCALS) - code_set)}, "
                      f"extra {sorted(code_set - (MAJORS | LOCALS))}")
    if len(code_set) != 16:
        errors.append("native set must contain exactly 16 currencies")

    enabled_external = []
    for asset in externals:
        code = asset.get("code")
        if asset.get("kind") != "external":
            errors.append(f"{code}: externalAssets entry is not kind external")
        if code in code_set:
            errors.append(f"{code}: external code collides with a native code")
        if asset.get("enabled"):
            enabled_external.append(code)
            if not asset.get("adapterUri"):
                errors.append(f"{code}: enabled without adapterUri")

    priority = config.get("priorityPairs") or []
    seen = set()
    for pair in priority:
        base, quote = pair.get("base"), pair.get("quote")
        if base == quote:
            errors.append(f"{base}/{quote}: self pair")
        if base not in code_set or quote not in code_set:
            errors.append(f"{base}/{quote}: unknown currency")
        key = tuple(sorted((base, quote)))
        if key in seen:
            errors.append(f"{base}/{quote}: duplicate unordered pair")
        seen.add(key)
    for local in LOCALS:
        if tuple(sorted((local, "USD"))) not in seen:
            errors.append(f"missing priority USD/{local}")
    for pair in [("USD", "EUR"), ("USD", "CNY"), ("EUR", "CNY")]:
        if tuple(sorted(pair)) not in seen:
            errors.append(f"missing priority hub pair {pair[0]}/{pair[1]}")

    expected_pairs = len(code_set) * (len(code_set) - 1) // 2
    if expected_pairs != 120:
        errors.append(f"full mesh should be 120 pairs, got {expected_pairs}")

    acceptance = yaml.safe_load(ACCEPTANCE.read_text())
    for index in range(1, 11):
        rid = f"SPEC-DEX-{index:02d}"
        entry = acceptance.get(rid)
        if not entry:
            errors.append(f"{rid}: missing acceptance entry")
            continue
        checks = {
            check
            for criterion in entry.get("criteria") or []
            for check in criterion.get("checks") or []
        }
        if not ({"static:mesh", "model:mesh"} & checks):
            errors.append(f"{rid}: no mesh or model evidence")

    for error in errors:
        print(f"ERROR [mesh] {error}", file=sys.stderr)
    if errors:
        print(f"mesh: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print(f"mesh: ok ({len(codes)} native, {len(enabled_external)} external, "
          f"{len(priority)} priority pairs, 120 unordered pairs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
