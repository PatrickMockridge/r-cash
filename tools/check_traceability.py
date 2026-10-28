#!/usr/bin/env python3
"""Requirement-level falsifiability gate.

Every MUST in docs/SPEC.md must have an entry in docs/spec/acceptance.yaml,
every acceptance criterion must be non-empty and name at least one declared
check, and every check ID must resolve in docs/spec/checks.yaml. Every flow
arm must name at least one acceptance criterion. Static/offline checks must
have a real artifact; campaign/platform checks are reported separately because
they run only in the final disposable-devnet campaign.

    python3 tools/check_traceability.py --report
    python3 tools/check_traceability.py --check --strict
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

import flowlib

ROOT = flowlib.ROOT
SPEC = ROOT / "docs" / "SPEC.md"
ACCEPTANCE = ROOT / "docs" / "spec" / "acceptance.yaml"
CHECKS = ROOT / "docs" / "spec" / "checks.yaml"
STATUSES = {"verified", "campaign", "platform", "draft", "blocked"}
REFUSAL_WORDS = re.compile(
    r"refus|reject|must not|invalid|wrong|duplicate|fail|blocked|forbid", re.I)


def spec_requirements() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in SPEC.read_text().splitlines():
        match = re.match(
            r"\| (SPEC-[A-Z]+-\d+) \| (MUST|SHOULD|MAY) \| (.*?) \| (.*?) \| (.*?) \|$",
            line,
        )
        if not match:
            continue
        rid, level, text, owner, status = match.groups()
        out[rid] = {"level": level, "text": text.strip(), "owner": owner.strip(),
                    "status": status.strip()}
    return out


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text())
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: not a mapping")
    return value


def check_artifact(root: Path, entry: dict) -> str | None:
    artifact = entry.get("artifact")
    if not artifact:
        return None
    path = root / artifact
    return None if path.exists() else f"missing artifact {artifact}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)
    errors: list[str] = []
    warnings: list[str] = []

    requirements = spec_requirements()
    acceptance = load_yaml(ACCEPTANCE)
    checks = load_yaml(CHECKS)

    # The manifest and the spec tables are the same set.
    for rid in sorted(set(requirements) - set(acceptance)):
        errors.append(f"{rid}: no acceptance entry")
    for rid in sorted(set(acceptance) - set(requirements)):
        errors.append(f"{rid}: acceptance entry has no SPEC row")
    for rid, entry in acceptance.items():
        req = requirements.get(rid)
        if req is None:
            continue
        if entry.get("level") != req["level"]:
            errors.append(f"{rid}: level {entry.get('level')} != {req['level']}")
        status = entry.get("status")
        if status not in STATUSES:
            errors.append(f"{rid}: unknown status {status!r}")
        if args.strict and status in ("draft", "blocked"):
            blocker = entry.get("blocker")
            errors.append(f"{rid}: status {status}" + (f" ({blocker})" if blocker else ""))
        criteria = entry.get("criteria") or []
        if not criteria:
            errors.append(f"{rid}: no acceptance criteria")
            continue
        negative = REFUSAL_WORDS.search(req["text"]) is not None
        negative_seen = False
        for criterion in criteria:
            cid = criterion.get("id") or "?"
            if not cid.startswith(f"AC-{rid}."):
                errors.append(f"{rid}: criterion id {cid} does not match AC-{rid}.N")
            for field in ("given", "when", "then"):
                if not str(criterion.get(field) or "").strip():
                    errors.append(f"{rid}/{cid}: empty {field}")
            names = criterion.get("checks") or []
            if not names:
                errors.append(f"{rid}/{cid}: no checks")
            for name in names:
                if name not in checks:
                    errors.append(f"{rid}/{cid}: unknown check {name!r}")
                    continue
                problem = check_artifact(ROOT, checks[name])
                if problem:
                    errors.append(f"{rid}/{cid}: {name}: {problem}")
                if checks[name].get("kind") == "platform":
                    warnings.append(f"{rid}/{cid}: platform-only evidence {name}")
            if REFUSAL_WORDS.search(str(criterion.get("then") or "")):
                negative_seen = True
        if negative and not negative_seen:
            warnings.append(f"{rid}: requirement mentions refusal but has no negative criterion")

    # Every flow arm names at least one existing acceptance criterion.
    accepted_ids = {
        criterion.get("id")
        for entry in acceptance.values()
        for criterion in entry.get("criteria") or []
    }
    arm_count = 0
    for doc, component, arm in flowlib.arms(flowlib.documents()):
        arm_count += 1
        refs = arm.get("acceptance") or []
        if not refs:
            errors.append(f"{doc['_path'].name}/{arm.get('arm', '?')}: no acceptance ID")
        for ref in refs:
            if ref not in accepted_ids:
                errors.append(f"{doc['_path'].name}/{arm.get('arm', '?')}: unknown acceptance {ref}")

    # Lean names referenced by rules and invariants, not only arms.
    lean = flowlib.lean_names(ROOT / "spec" / "lean")
    for doc in flowlib.documents():
        for invariant, value in (doc.get("invariants") or {}).items():
            name = value.get("lean") if isinstance(value, dict) else None
            if name and lean and name not in lean:
                errors.append(f"{doc['_path'].name}/{invariant}: Lean {name} missing")
        for rule in doc.get("rules") or []:
            name = rule.get("lean")
            if name and lean and name not in lean:
                errors.append(f"{doc['_path'].name}/{rule.get('id', '?')}: Lean {name} missing")

    status_counts = Counter(entry.get("status") for entry in acceptance.values())
    kind_counts = Counter(
        checks[name].get("kind")
        for entry in acceptance.values()
        for criterion in entry.get("criteria") or []
        for name in criterion.get("checks") or []
        if name in checks
    )
    if args.report or not args.check:
        for error in errors:
            print(f"ERROR [traceability] {error}")
        for warning in warnings:
            print(f"WARNING [traceability] {warning}")
        print(f"requirements: {len(requirements)} MUST, {len(acceptance)} accepted, "
              f"{arm_count} arms")
        print(f"statuses: {dict(sorted(status_counts.items()))}")
        print(f"checks: {dict(sorted(kind_counts.items()))}")
        print(f"traceability: {len(errors)} error(s), {len(warnings)} warning(s)")
    if args.check and errors:
        for error in errors:
            print(f"ERROR [traceability] {error}", file=sys.stderr)
        return 1
    if args.check:
        print(f"traceability: ok ({len(requirements)} requirements, {arm_count} arms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
