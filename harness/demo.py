#!/usr/bin/env python3
"""Run the packaged demo on a fresh devnet: bootstrap -> pool -> book -> scenarios."""
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
steps = [
    ["harness/bootstrap.py"],
    ["harness/pool_bootstrap.py"],
    ["harness/transfer_bootstrap.py"],
    ["harness/scenarios/pool.py"],
    ["harness/scenarios/transfer.py"],
]
for step in steps:
    print(f"\n==> {' '.join(step)}", flush=True)
    r = subprocess.run([sys.executable, *step], cwd=ROOT)
    if r.returncode != 0:
        print(f"demo stopped at {' '.join(step)}", file=sys.stderr)
        raise SystemExit(r.returncode)
print("\ndemo complete")
