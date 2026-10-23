#!/usr/bin/env python3
"""Resolve `// @@INLINE:lib/file.rho@@` markers into deployable Rholang terms.

Rholang has no imports.  A source file declares the library contract names in its outer `new`
and marks the insertion point; this script pastes the library's contract definitions there.  The
result is written under `contracts/build/` (committed for auditability).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "contracts" / "src"
OUT = ROOT / "contracts" / "build"
MARKER = re.compile(r"^\s*//\s*@@INLINE:([^@]+)@@\s*$", re.MULTILINE)


def check_braces(text: str, label: str) -> None:
    """Reject a fragment whose brace depth goes negative or does not return to zero.

    A globally balanced file can still hide a per-contract scope error (the v0.2
    ListingRegistry had an extra `}` and a missing `}` that cancelled). Negative depth
    catches the extra close; a nonzero final depth catches the missing one.
    """
    depth = 0
    in_string = False
    escaped = False
    for number, line in enumerate(text.splitlines(), start=1):
        index = 0
        while index < len(line):
            char = line[index]
            if not in_string and char == "/" and index + 1 < len(line) and line[index + 1] == "/":
                break
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth < 0:
                        raise SystemExit(f"{label}:{number}: brace depth went negative")
            index += 1
    if depth != 0:
        raise SystemExit(f"{label}: unclosed braces (depth {depth})")


def render(path: Path) -> tuple[Path, str]:
    text = path.read_text()

    def replace(match: re.Match[str]) -> str:
        lib = (SRC / match.group(1).strip()).resolve()
        if not lib.is_file():
            raise SystemExit(f"{path}: missing inline library {lib}")
        body = lib.read_text().rstrip("\n")
        check_braces(body, str(lib.relative_to(ROOT)))
        return f"// ---- begin {match.group(1).strip()} ----\n{body}\n// ---- end {match.group(1).strip()} ----"

    built = text
    # Markers can nest (AccountFactory inlines AccountBody). Resolve to a fixed point.
    for _ in range(8):
        nxt = MARKER.sub(replace, built)
        if nxt == built:
            break
        built = nxt
    if "@@INLINE:" in built:
        raise SystemExit(f"{path}: unresolved inline marker remains")
    check_braces(built, str(path.relative_to(ROOT)))
    return OUT / path.relative_to(SRC), built


def build_one(path: Path, check: bool = False) -> Path:
    dest, built = render(path)
    if check:
        if not dest.is_file() or dest.read_text() != built:
            raise SystemExit(f"drift: {dest.relative_to(ROOT)} is stale")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(built)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="build to memory and fail on drift")
    args = ap.parse_args(argv)

    # Only deploy terms are built. Library contracts under core/, dex/, lib/,
    # listing/, lock/, oracle/, stable/ and transfer/ are Rholang `.rho` includes
    # resolved through @@INLINE markers; building them directly would emit
    # non-deployable fragments.
    sources = sorted((SRC / "deploy").rglob("*.rho"))
    if not sources:
        print("no contract sources found", file=sys.stderr)
        return 1
    expected: set[Path] = set()
    for src in sources:
        dest = build_one(src, check=args.check)
        expected.add(dest.resolve())
        if args.check:
            print(f"ok {dest.relative_to(ROOT)}")
        else:
            print(f"built {dest.relative_to(ROOT)}")

    # A removed/renamed source must not leave a stale deploy term behind.
    stale = [
        path for path in OUT.rglob("*.rho") if path.resolve() not in expected
    ]
    if stale:
        if args.check:
            for path in stale:
                print(f"stale {path.relative_to(ROOT)}", file=sys.stderr)
            return 1
        for path in stale:
            path.unlink()
            print(f"removed stale {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
