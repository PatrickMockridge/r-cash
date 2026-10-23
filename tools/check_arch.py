#!/usr/bin/env python3
"""Validate the v0.3 component catalogue.

Checks:
  - unique component names and unique state-cell ownership;
  - every call dependency names a declared component;
  - the call graph is acyclic (factory creation edges are separate);
  - every `creates` target is declared;
  - implemented components have a built deploy term;
  - no v3 deploy term inlines a component;
  - implemented deploy terms are within the hard byte/depth/contract budgets.

Usage:
    python3 tools/check_arch.py            # report
    python3 tools/check_arch.py --check    # fail on any problem
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "contracts" / "components.json"
BUILD = ROOT / "contracts" / "build"
MANIFEST = BUILD / "manifest.json"
INLINE = re.compile(r"@@INLINE:([^@]+)@@")


def load() -> tuple[dict, list[dict], dict[str, dict]]:
    data = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    components = data.get("components", [])
    by_name = {c["name"]: c for c in components}
    return data, components, by_name


def check_names(components: list[dict], by_name: dict[str, dict]) -> list[str]:
    problems: list[str] = []
    if len(by_name) != len(components):
        problems.append("duplicate component names")
    owners: dict[str, str] = {}
    for component in components:
        cell = component.get("state_cell")
        if component.get("stateful"):
            if not cell:
                problems.append(f"{component['name']}: stateful without a state_cell")
            elif cell in owners:
                problems.append(
                    f"state cell {cell!r} owned by both {owners[cell]} and {component['name']}"
                )
            else:
                owners[cell] = component["name"]
        elif cell:
            problems.append(f"{component['name']}: stateless but declares state_cell {cell!r}")
    return problems


def check_edges(components: list[dict], by_name: dict[str, dict]) -> list[str]:
    problems: list[str] = []
    for component in components:
        for dependency in component.get("dependencies", []):
            if dependency.startswith("rho:"):
                continue
            if dependency not in by_name:
                problems.append(f"{component['name']}: unknown dependency {dependency}")
        for created in component.get("creates", []):
            if created not in by_name:
                problems.append(f"{component['name']}: unknown created component {created}")
    return problems


def check_acyclic(components: list[dict], by_name: dict[str, dict]) -> list[str]:
    problems: list[str] = []
    graph = {c["name"]: [d for d in c.get("dependencies", []) if d in by_name] for c in components}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(name: str) -> None:
        state[name] = 1
        stack.append(name)
        for dependency in graph.get(name, []):
            if state.get(dependency) == 1:
                cycle = stack[stack.index(dependency):] + [dependency]
                problems.append("dependency cycle: " + " -> ".join(cycle))
            elif state.get(dependency, 0) == 0:
                visit(dependency)
        stack.pop()
        state[name] = 2

    for name in graph:
        if state.get(name, 0) == 0:
            visit(name)
    return problems


def built_path(deploy: str) -> str:
    if deploy.startswith("contracts/src/"):
        return "contracts/build/" + deploy[len("contracts/src/"):]
    return deploy


def check_builds(components: list[dict], budgets: dict) -> list[str]:
    problems: list[str] = []
    manifest: dict = {}
    if MANIFEST.is_file():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8")).get("entries", {})

    bytes_fail = budgets.get("bytes_fail", 57344)
    depth_fail = budgets.get("depth_fail", 96)
    contracts_fail = budgets.get("contracts_fail", 12)
    checked: set[str] = set()

    for component in components:
        if component.get("status") != "implemented":
            continue
        deploy = component.get("deploy")
        if not deploy:
            problems.append(f"{component['name']}: implemented without a deploy path")
            continue
        built = built_path(deploy)
        if built in checked:
            continue
        checked.add(built)
        if built not in manifest:
            problems.append(f"{component['name']}: {built} is not in the build manifest")
            continue
        entry = manifest[built]
        if entry.get("minified_bytes", 0) > bytes_fail:
            problems.append(f"{built}: {entry['minified_bytes']} bytes > {bytes_fail}")
        if entry.get("grammar_depth", 0) > depth_fail:
            problems.append(f"{built}: depth {entry['grammar_depth']} > {depth_fail}")
        if entry.get("contracts", 0) > contracts_fail:
            problems.append(f"{built}: {entry['contracts']} contracts > {contracts_fail}")
    return problems


def check_inline() -> list[str]:
    problems: list[str] = []
    v3 = ROOT / "contracts" / "src" / "deploy" / "v3"
    if not v3.is_dir():
        return problems
    for path in sorted(v3.rglob("*.rho")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = INLINE.search(line)
            if match:
                problems.append(
                    f"{path.relative_to(ROOT)}:{number}: v3 may not inline {match.group(1).strip()}"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail on any problem")
    args = ap.parse_args(argv)

    data, components, by_name = load()
    problems: list[str] = []
    problems += check_names(components, by_name)
    problems += check_edges(components, by_name)
    problems += check_acyclic(components, by_name)
    problems += check_builds(components, data.get("budgets", {}))
    problems += check_inline()

    if problems:
        print("architecture problems:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1 if args.check else 0

    stateful = sum(1 for c in components if c.get("stateful"))
    implemented = sum(1 for c in components if c.get("status") == "implemented")
    print(
        f"architecture: ok ({len(components)} components, {stateful} stateful, "
        f"{implemented} implemented)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
