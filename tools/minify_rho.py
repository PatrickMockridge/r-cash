#!/usr/bin/env python3
"""Conservative Rholang minifier for the node's 65,536-byte deploy-term limit.

Removes `//` comments (string-aware) and leading/trailing indentation, and drops blank lines.
Newlines between lines are preserved, so token separation is never lost. This is intentional: an
aggressive whitespace collapse broke a parse once, and the conservative form is enough to fit the
bootstrap under the limit.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _strip_comment(line: str) -> str:
    out: list[str] = []
    i = 0
    n = len(line)
    in_string = False
    escaped = False
    while i < n:
        c = line[i]
        if in_string:
            out.append(c)
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
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and line[i + 1] == "/":
            break
        out.append(c)
        i += 1
    return "".join(out)


def minify(src: str) -> str:
    lines = []
    for line in src.splitlines():
        stripped = _strip_comment(line).strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: minify_rho.py <in.rho> <out.rho>", file=sys.stderr)
        return 2
    Path(args[1]).write_text(minify(Path(args[0]).read_text()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
