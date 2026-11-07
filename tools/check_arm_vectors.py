#!/usr/bin/env python3
"""Compare the Lean arm-vector output with tests/vectors/arms.json.

    python3 tools/check_arm_vectors.py --check

The emitter is `spec/lean/Rholphin/EmitArms.lean`; it prints
`name|inputs|output` lines.  A missing or extra vector is an error, so a new
arm vector cannot be added without recording its expected output.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEAN = ROOT / "spec" / "lean"
EMITTER = "Rholphin/EmitArms.lean"
VECTORS = ROOT / "tests" / "vectors" / "arms.json"


def parse(stdout: str) -> dict[str, tuple[list[int], str]]:
    out: dict[str, tuple[list[int], str]] = {}
    for line in stdout.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3:
            continue
        name, inputs, value = parts
        out[name] = ([int(item) for item in inputs.split(",") if item], value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    expected = json.loads(VECTORS.read_text())
    run = subprocess.run(
        ["lake", "env", "lean", EMITTER],
        cwd=LEAN,
        text=True,
        capture_output=True,
    )
    if run.returncode != 0:
        sys.stderr.write(run.stdout)
        sys.stderr.write(run.stderr)
        print("arm-vectors: emitter failed", file=sys.stderr)
        return 1

    actual = parse(run.stdout)
    errors: list[str] = []
    for name, spec in expected.items():
        if name not in actual:
            errors.append(f"{name}: missing from the emitter")
            continue
        inputs, value = actual[name]
        if inputs != spec["inputs"]:
            errors.append(f"{name}: inputs {inputs} != {spec['inputs']}")
        if value != spec["out"]:
            errors.append(f"{name}: output {value} != {spec['out']}")
    for name in sorted(set(actual) - set(expected)):
        errors.append(f"{name}: emitted but not recorded in arms.json")

    print(f"arm-vectors: {len(expected)} vectors, {len(errors)} error(s)")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors and args.check:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
