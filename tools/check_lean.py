#!/usr/bin/env python3
"""Build the Lean model, reject sorry/admit/axiom, and audit the axioms.

    python3 tools/check_lean.py

The project is pinned by `spec/lean/lean-toolchain` (Lean 4.12) and has no
Mathlib dependency.  The audit runs `#print axioms` from `Rholphin/Audit.lean`
and accepts only the three core axioms Lean may introduce (`propext`,
`Classical.choice`, `Quot.sound`).  `sorryAx` is never accepted.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEAN = ROOT / "spec" / "lean"
AUDIT = "Rholphin/Audit.lean"

FORBIDDEN = re.compile(r"(?<!#)\b(sorry|admit|native_decide)\b|^\s*axiom\s+[A-Za-z_]")
ALLOWED = {"propext", "Classical.choice", "Quot.sound"}


def source_scan() -> list[str]:
    problems: list[str] = []
    for path in sorted(LEAN.rglob("*.lean")):
        text = path.read_text()
        for number, line in enumerate(text.splitlines(), start=1):
            code = line.split("--", 1)[0]
            if FORBIDDEN.search(code):
                problems.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    return problems


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=LEAN, text=True, capture_output=True)


def main() -> int:
    problems = source_scan()
    for problem in problems:
        print(f"forbidden proof escape: {problem}", file=sys.stderr)

    build = run(["lake", "build"])
    if build.returncode != 0:
        sys.stderr.write(build.stdout)
        sys.stderr.write(build.stderr)
        print("lean: build failed", file=sys.stderr)
        return 1

    audit = run(["lake", "env", "lean", AUDIT])
    if audit.returncode != 0:
        sys.stderr.write(audit.stdout)
        sys.stderr.write(audit.stderr)
        print("lean: audit failed", file=sys.stderr)
        return 1

    lines = [line for line in audit.stdout.splitlines() if "depends on axioms" in line]
    if len(lines) < 20:
        print(f"lean: audit produced only {len(lines)} axiom lines", file=sys.stderr)
        return 1
    for line in lines:
        match = re.search(r"depends on axioms: \[(.*?)\]", line)
        if not match:
            continue
        used = {axiom.strip() for axiom in match.group(1).split(",") if axiom.strip()}
        extra = used - ALLOWED
        if extra:
            print(f"lean: unexpected axiom(s) {sorted(extra)} in {line}", file=sys.stderr)
            return 1
        if "sorryAx" in used:
            print(f"lean: sorryAx in {line}", file=sys.stderr)
            return 1

    if problems:
        return 1
    print(f"lean: built, {len(lines)} axiom audits, no sorry/admit/axiom/native_decide")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
