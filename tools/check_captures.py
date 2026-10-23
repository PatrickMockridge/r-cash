#!/usr/bin/env python3
"""Detect bundled contracts that capture registry-resolved capabilities.

The `03_accounts` continuation failure is the motivating case: a deploy reads a
live capability from a registry and bundles a contract whose closure captures it.
v0.3 forbids that pattern; a bundle may close over only system channels, values,
its own cells and locally created names.

This is a lexical first pass. The authoritative gate is empirical: deploy the
component, cross a block boundary, call it again, and fail on a continuation
decode error (see harness/install_v3.py).

Usage:
    python3 tools/check_captures.py                  # report
    python3 tools/check_captures.py --check          # fail on new findings vs baseline
    python3 tools/check_captures.py --strict         # fail on any finding
    python3 tools/check_captures.py --write-baseline # record the current findings
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "contracts" / "src"
BASELINE = ROOT / "tools" / "capture_baseline.json"

REGISTRY_CALL = re.compile(
    r"(Components!|Directory!|ListingRegistry!|Root!|StablecoinDirectory!|"
    r"OracleRegistry!|MarketDirectory!|CurrencyRegistry!|rl!)"
    r"\s*\((.*?)\)",
    re.S,
)
RECEIVE = re.compile(r"for\s*\(([^)]*)\)\s*(?:<-|<<-)\s*([A-Za-z_][A-Za-z0-9_]*)")
BUNDLE = re.compile(r"bundle\+?\{\s*\*([A-Za-z_][A-Za-z0-9_]*)\s*\}")


def strip_comments(text: str) -> str:
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


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def registry_channels(text: str) -> set[str]:
    channels: set[str] = set()
    for match in REGISTRY_CALL.finditer(text):
        call, args = match.group(1), match.group(2)
        if call == "rl!":
            first = args.split(",", 1)[0].strip()
            # System channels are allowed in a bundle. Only app URIs are a capture risk.
            if first.startswith("`rho:") or first.startswith('"rho:'):
                continue
        for name in re.findall(r"\*([A-Za-z_][A-Za-z0-9_]*)", args):
            channels.add(name)
    return channels


def matching_brace(text: str, start: int) -> int:
    """Return the index of the `}` matching the `{` at or after start."""
    index = text.find("{", start)
    if index < 0:
        return -1
    depth = 0
    in_string = False
    escaped = False
    i = index
    while i < len(text):
        c = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def findings_for(path: Path) -> list[dict]:
    text = strip_comments(path.read_text(encoding="utf-8"))
    channels = registry_channels(text)
    findings: list[dict] = []
    seen: set[tuple[int, str]] = set()

    for match in RECEIVE.finditer(text):
        pattern, channel = match.group(1), match.group(2)
        if channel not in channels:
            continue
        end = matching_brace(text, match.end())
        if end < 0:
            continue
        block = text[match.end():end]
        for bundle in BUNDLE.finditer(block):
            name = bundle.group(1)
            key = (line_of(text, match.start()), name)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "line": line_of(text, match.start()),
                    "kind": "registry-scope-bundle",
                    "name": name,
                    "channel": channel,
                }
            )

    for bundle in BUNDLE.finditer(text):
        name = bundle.group(1)
        # A contract that is itself bound from a registry channel and then bundled.
        for match in RECEIVE.finditer(text):
            pattern, channel = match.group(1), match.group(2)
            if channel in channels and re.search(rf"\b{re.escape(name)}\b", pattern):
                key = (line_of(text, bundle.start()), name)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    {
                        "file": str(path.relative_to(ROOT)),
                        "line": line_of(text, bundle.start()),
                        "kind": "registry-bound-bundle",
                        "name": name,
                        "channel": channel,
                    }
                )
    return findings


def scan() -> list[dict]:
    findings: list[dict] = []
    for path in sorted(SRC.rglob("*.rho")):
        findings.extend(findings_for(path))
    findings.sort(key=lambda f: (f["file"], f["line"], f["kind"], f["name"]))
    return findings


def key(finding: dict) -> str:
    return f"{finding['file']}:{finding['line']}:{finding['kind']}:{finding['name']}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail on new findings vs baseline")
    ap.add_argument("--strict", action="store_true", help="fail on any finding")
    ap.add_argument("--write-baseline", action="store_true", help="record current findings")
    args = ap.parse_args(argv)

    findings = scan()
    baseline: set[str] = set()
    if BASELINE.is_file():
        baseline = set(json.loads(BASELINE.read_text(encoding="utf-8")).get("keys", []))

    if args.write_baseline:
        BASELINE.write_text(
            json.dumps({"keys": sorted(key(f) for f in findings)}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {len(findings)} baseline findings to {BASELINE.relative_to(ROOT)}")
        return 0

    if args.strict:
        problems = findings
    elif args.check:
        problems = [f for f in findings if key(f) not in baseline]
    else:
        problems = []

    for finding in findings:
        known = key(finding) in baseline
        label = "known" if known else "new"
        print(
            f"{label}: {finding['file']}:{finding['line']} "
            f"{finding['kind']} {finding['name']} via {finding['channel']}"
        )

    if problems:
        print("capture findings not in the baseline:", file=sys.stderr)
        for finding in problems:
            print(f"  {key(finding)}", file=sys.stderr)
        return 1
    print(f"captures: ok ({len(findings)} findings, {len(baseline)} baselined)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
