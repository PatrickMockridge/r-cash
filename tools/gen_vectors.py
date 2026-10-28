#!/usr/bin/env python3
"""Generate deterministic vectors from the Lean model.

    python3 tools/gen_vectors.py --write   # write tests/vectors/arith.json
    python3 tools/gen_vectors.py --check   # fail if the committed file is stale

The vector source is `spec/lean/Rholphin/Emit.lean`; no arithmetic is
reimplemented here. Output lines are `name|input,...|output`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEAN = ROOT / "spec" / "lean"
OUT = ROOT / "tests" / "vectors" / "arith.json"


def generate() -> dict:
    proc = subprocess.run(
        ["lake", "env", "lean", "Rholphin/Emit.lean"],
        cwd=LEAN, text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit("lean vector emission failed")
    vectors = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("Rholphin/"):
            continue
        parts = line.split("|")
        if len(parts) != 3:
            raise SystemExit(f"bad vector line: {line!r}")
        name, inputs, output = parts
        values = [int(value) for value in inputs.split(",") if value]
        outs = [int(value) for value in output.split(",") if value]
        vectors[name] = {"inputs": values,
                         "output": outs[0] if len(outs) == 1 else outs}
    if len(vectors) < 20:
        raise SystemExit(f"only {len(vectors)} vectors emitted")
    return dict(sorted(vectors.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = json.dumps(generate(), indent=2, sort_keys=True) + "\n"
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text)
        print(f"wrote {OUT.relative_to(ROOT)}")
        return 0
    if args.check:
        if not OUT.is_file() or OUT.read_text() != text:
            print(f"stale {OUT.relative_to(ROOT)}; run tools/gen_vectors.py --write",
                  file=sys.stderr)
            return 1
        print(f"vectors: ok ({len(json.loads(text))} cases)")
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
