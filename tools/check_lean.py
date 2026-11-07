#!/usr/bin/env python3
"""Build the Lean model, reject sorry/admit/axiom, and audit the axioms.

    python3 tools/check_lean.py

The project is pinned by `spec/lean/lean-toolchain` (Lean 4.12) and has no
Mathlib dependency.  The audit runs `#print axioms` from `Rholphin/Audit.lean`
and accepts only the three core axioms Lean may introduce (`propext`,
`Classical.choice`, `Quot.sound`).  `sorryAx` is never accepted.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEAN = ROOT / "spec" / "lean"
AUDIT = "Rholphin/Audit.lean"
CLAIMS = ROOT / "tools" / "check_claims.py"

FORBIDDEN = re.compile(r"(?<!#)\b(sorry|admit|native_decide)\b|^\s*axiom\s+[A-Za-z_]")
ALLOWED = {"propext", "Classical.choice", "Quot.sound"}


def strip_strings(line: str) -> str:
    """Blank the contents of double-quoted strings, preserving positions.

    Proof-escape scanning must not fire on identifiers or prose inside a
    string literal (for example a vector name containing `admit`).
    """
    out: list[str] = []
    in_string = False
    escaped = False
    for char in line:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            out.append(" ")
        else:
            if char == '"':
                in_string = True
                out.append(" ")
            else:
                out.append(char)
    return "".join(out)


def source_scan() -> list[str]:
    problems: list[str] = []
    for path in sorted(LEAN.rglob("*.lean")):
        text = path.read_text()
        for number, line in enumerate(text.splitlines(), start=1):
            code = strip_strings(line.split("--", 1)[0])
            if FORBIDDEN.search(code):
                problems.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    return problems


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=LEAN, text=True, capture_output=True)


def warnings() -> list[str]:
    """Report modules that emit warnings under `-DwarningAsError=true`.

    Report-only for now: Phase 4 removes the weak hypotheses that produce most
    of these, then the flag becomes blocking.
    """
    out: list[str] = []
    for path in sorted((LEAN / "Rholphin").rglob("*.lean")):
        relative = path.relative_to(LEAN)
        check = run(["lake", "env", "lean", "-DwarningAsError=true", str(relative)])
        if check.returncode != 0:
            first = next(
                (line for line in check.stdout.splitlines() if "warning" in line.lower()),
                check.stdout.splitlines()[0] if check.stdout.splitlines() else "build error",
            )
            out.append(f"{relative}: {first.strip()}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warnings", action="store_true", help="report warning-as-error modules")
    args = parser.parse_args()

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

    claims = subprocess.run(
        [sys.executable, str(CLAIMS), "--check", "--strict-arms"], cwd=ROOT, text=True, capture_output=True
    )
    sys.stdout.write(claims.stdout)
    sys.stderr.write(claims.stderr)
    if claims.returncode != 0:
        print("lean: claim register failed", file=sys.stderr)
        return 1

    if args.warnings:
        warned = warnings()
        for item in warned:
            print(f"lean warning: {item}", file=sys.stderr)
        print(f"lean: {len(warned)} modules emit warnings")

    if problems:
        return 1
    print(f"lean: built, {len(lines)} axiom audits, no sorry/admit/axiom/native_decide")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
