#!/usr/bin/env python3
"""Measure built Rholang terms against the platform budgets.

The node accepts at most 65,536 UTF-8 bytes per deploy term and parses at most
128 grammar productions of nesting. This tool reports the minified byte count,
a conservative structural depth and the longest operator run for every term
under contracts/build, and writes a deterministic manifest for CI drift checks.

It is deliberately conservative: the exact parser depth is available only
inside the node, and linking that parser here would add a native build step the
language policy forbids. The devnet parse/normalize step is the authoritative
check.

Usage:
    python3 tools/measure_contracts.py             # print the table
    python3 tools/measure_contracts.py --write     # write contracts/build/manifest.json
    python3 tools/measure_contracts.py --check     # fail if the manifest is stale
    python3 tools/measure_contracts.py --budget    # enforce budgets on v3 units
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "contracts" / "build"
MANIFEST = BUILD / "manifest.json"
COMPONENTS = ROOT / "contracts" / "components.json"

sys.path.insert(0, str(ROOT / "tools"))
from minify_rho import minify  # noqa: E402

KEYWORDS = {"contract", "for", "match", "if", "new", "bundle", "case", "let", "select"}
OPENERS = {"{", "(", "["}
CLOSERS = {"}": "{", ")": "(", "]": "["}
OPERATORS = {
    "+", "-", "*", "/", "%", "++", "<", ">", "<=", ">=", "==", "!=",
    "&&", "||", "^", "<<", ">>",
}
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|\"(?:\\.|[^\"\\])*\"|<-|<<-|\+\+|==|!=|<=|>=|&&|\|\||\S")


def strip_comments(text: str) -> str:
    """Remove // comments while preserving string contents."""
    out: list[str] = []
    for line in text.splitlines():
        in_string = False
        escaped = False
        kept: list[str] = []
        i = 0
        while i < len(line):
            c = line[i]
            if in_string:
                kept.append(c)
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    in_string = False
                i += 1
                continue
            if c == '"':
                in_string = True
                kept.append(c)
                i += 1
                continue
            if c == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            kept.append(c)
            i += 1
        out.append("".join(kept))
    return "\n".join(out)


def metrics(text: str) -> dict[str, int]:
    clean = strip_comments(text)
    tokens = TOKEN.findall(clean)

    bracket_depth = 0
    max_bracket = 0
    keyword_depth = 0
    max_grammar = 0
    frames: list[str | None] = []
    pending_keyword: str | None = None
    contracts = 0

    for token in tokens:
        if token in KEYWORDS:
            if token == "contract":
                contracts += 1
            pending_keyword = token
            continue
        if token in OPENERS:
            frames.append(pending_keyword)
            bracket_depth += 1
            if pending_keyword is not None and pending_keyword in KEYWORDS - {"let"}:
                keyword_depth += 1
            max_bracket = max(max_bracket, bracket_depth)
            max_grammar = max(max_grammar, bracket_depth + keyword_depth)
            pending_keyword = None
            continue
        if token in CLOSERS:
            opener = CLOSERS[token]
            keyword = frames.pop() if frames else None
            bracket_depth = max(0, bracket_depth - 1)
            if keyword is not None and keyword in KEYWORDS - {"let"}:
                keyword_depth = max(0, keyword_depth - 1)
            if opener == "(" and keyword is not None:
                # Carry for/match/if across a parenthesised head into its body.
                pending_keyword = keyword
            else:
                pending_keyword = None
            continue
        if token in {"|", ";"}:
            pending_keyword = None
            continue

    max_ops_line = 0
    for line in clean.splitlines():
        count = sum(1 for token in TOKEN.findall(line) if token in OPERATORS)
        max_ops_line = max(max_ops_line, count)

    raw = text.encode()
    mini = minify(text).encode()
    return {
        "source_bytes": len(raw),
        "minified_bytes": len(mini),
        "brace_depth": max_bracket,
        "grammar_depth": max_grammar,
        "operator_run": max_ops_line,
        "contracts": contracts,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def measure() -> dict:
    entries = {}
    for path in sorted(BUILD.rglob("*.rho")):
        rel = str(path.relative_to(ROOT))
        entries[rel] = metrics(path.read_text(encoding="utf-8"))
    return {"schema": "rcash:contract-metrics:v1", "entries": entries}


def load_budgets() -> dict:
    data = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    return data.get("budgets", {})


def check_budgets(manifest: dict, budgets: dict) -> list[str]:
    problems: list[str] = []
    bytes_fail = budgets.get("bytes_fail", 57344)
    depth_fail = budgets.get("depth_fail", 96)
    contracts_fail = budgets.get("contracts_fail", 12)
    v3 = {
        path: entry
        for path, entry in manifest["entries"].items()
        if "/v3/" in path or path.endswith("/v3")
    }
    if not v3:
        print("budget: no v3 units yet; nothing to enforce")
        return []
    overrides = budgets.get("overrides", {})
    for path, entry in sorted(v3.items()):
        local = overrides.get(path, {})
        local_bytes = local.get("bytes", bytes_fail)
        local_depth = local.get("depth", depth_fail)
        local_contracts = local.get("contracts", contracts_fail)
        if entry["minified_bytes"] > local_bytes:
            problems.append(f"{path}: {entry['minified_bytes']} bytes > {local_bytes}")
        if entry["grammar_depth"] > local_depth:
            problems.append(f"{path}: depth {entry['grammar_depth']} > {local_depth}")
        if entry["contracts"] > local_contracts:
            problems.append(f"{path}: {entry['contracts']} contracts > {local_contracts}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write contracts/build/manifest.json")
    ap.add_argument("--check", action="store_true", help="fail if the manifest is stale")
    ap.add_argument("--budget", action="store_true", help="enforce v3 budgets")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = ap.parse_args(argv)

    if not BUILD.is_dir():
        print("no contracts/build directory; run tools/build_contracts.py", file=sys.stderr)
        return 1

    current = measure()
    text = json.dumps(current, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not MANIFEST.is_file():
            print(f"missing {MANIFEST.relative_to(ROOT)}; run --write", file=sys.stderr)
            return 1
        if MANIFEST.read_text(encoding="utf-8") != text:
            print("drift: contracts/build/manifest.json is stale", file=sys.stderr)
            return 1
    if args.write:
        MANIFEST.write_text(text, encoding="utf-8")

    if args.budget:
        problems = check_budgets(current, load_budgets())
        if problems:
            print("budget failures:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1

    if args.json:
        print(text, end="")
    elif not args.write and not args.check and not args.budget:
        print(f"{'term':58} {'bytes':>7} {'depth':>6} {'ops':>4} {'contracts':>9}")
        for path, entry in sorted(current["entries"].items()):
            print(
                f"{path:58} {entry['minified_bytes']:>7} "
                f"{entry['grammar_depth']:>6} {entry['operator_run']:>4} "
                f"{entry['contracts']:>9}"
            )
    if args.check:
        print(f"ok {MANIFEST.relative_to(ROOT)}")
    if args.budget:
        print("ok budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
