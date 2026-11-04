#!/usr/bin/env python3
"""Mechanical checks for the primitive conventions in the deploy sources.

These are deliberately small, high-signal rules.  They do not replace the flow
checker; they close the specific gaps the primitives audit identified:

  G-NATIVE  no native reply is discarded with `for (_ <- ...)`;
  G-REV     a registry that mutates a rev-bearing cell bumps `rev`;
  ORACLE    `oracleRegState` is initialised with `rev` and `regBind` bumps it.

The checks are textual.  They are a regression guard for the shapes that were
fixed, not a proof that every future arm is correct.

    python3 tools/check_primitives.py --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts" / "src" / "deploy" / "v3"

DISCARDED_REPLY = re.compile(r"for\s*\(\s*_\s*<-")
TAKE_CELL = re.compile(r"for\s*\(\s*@?\w+\s*<-\s*([A-Za-z_]\w*State)\b")
SET_REV = re.compile(r"\.set\(\s*\"rev\"")
ORACLE_INIT = re.compile(r"oracleRegState!\(\{(.*?)\}\)", re.S)

# Cells that carry a `rev` field and must be bumped on mutation.
REV_CELLS = {
    "accountState",
    "bufferState",
    "currencyState",
    "directoryState",
    "feedState",
    "indexState",
    "issuerState",
    "oracleRegState",
    "poolState",
    "psmState",
    "savingsState",
    "termsState",
    "vaultState",
}

# `issuerState` uses totalPrincipal as its compare-and-swap field, not `rev`.
REV_EXEMPT = {"issuerState"}


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def check_file(path: Path, errors: list[str], warnings: list[str]) -> None:
    text = path.read_text()
    relative = path.relative_to(ROOT)

    for match in DISCARDED_REPLY.finditer(text):
        errors.append(
            f"{relative}:{line_of(text, match.start())}: native reply discarded "
            f"with `for (_ <- ...)`; match the reply and fail closed"
        )

    if "oracleRegState!({" in text:
        init = ORACLE_INIT.search(text)
        if not init or '"rev"' not in init.group(1):
            errors.append(f"{relative}: oracleRegState initial state has no `rev`")
        if "regBind" in text and not SET_REV.search(text):
            errors.append(f"{relative}: regBind mutates oracleRegState without bumping `rev`")

    mutated = {cell for cell in TAKE_CELL.findall(text) if cell in REV_CELLS}
    if mutated and not SET_REV.search(text):
        errors.append(
            f"{relative}: mutates rev-bearing cell(s) {sorted(mutated)} but never bumps `rev`"
        )
    for cell in sorted(mutated & REV_EXEMPT):
        warnings.append(f"{relative}: {cell} uses its own CAS field; confirm no `rev` is expected")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    files = sorted(CONTRACTS.glob("*.rho"))
    for path in files:
        check_file(path, errors, warnings)

    print(f"primitives: {len(files)} files, {len(errors)} error(s), {len(warnings)} warning(s)")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors and args.check:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
