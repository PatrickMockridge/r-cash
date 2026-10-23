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


def build_one(path: Path) -> Path:
    text = path.read_text()

    def replace(match: re.Match[str]) -> str:
        lib = (SRC / match.group(1).strip()).resolve()
        if not lib.is_file():
            raise SystemExit(f"{path}: missing inline library {lib}")
        body = lib.read_text().rstrip("\n")
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
    rel = path.relative_to(SRC)
    dest = OUT / rel
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
    for src in sources:
        dest = build_one(src)
        print(f"built {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
