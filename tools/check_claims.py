#!/usr/bin/env python3
"""Check the Lean claim register (`spec/lean/claims.yaml`).

The register is the audit's coverage contract.  This tool enforces four things:

  1. every invariant in docs/spec/20-INVARIANTS.md has an entry;
  2. every named Lean theorem resolves to a declaration in spec/lean;
  3. every `covered` invariant cites at least one `substantive` theorem;
  4. a theorem declared `substantive` is not a hypothesis restatement
     (`:= h`, `:= rfl`, `exact h`, `simpa ... using h`).

It also cross-checks the `invariants:` entries in docs/spec/flows/*.yaml and
reports which claim theorems are not in the axiom audit.

    python3 tools/check_claims.py            # report
    python3 tools/check_claims.py --check    # fail on a structural defect

Exit codes: 0 ok (report mode always 0 unless the register cannot be read),
1 structural defect, 2 missing input.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "spec" / "lean" / "claims.yaml"
LEAN = ROOT / "spec" / "lean"
INVARIANTS = ROOT / "docs" / "spec" / "20-INVARIANTS.md"
FLOWS = ROOT / "docs" / "spec" / "flows"
AUDIT = LEAN / "Rholphin" / "Audit.lean"

STATUSES = {"covered", "partial", "deferred", "tool"}
STRENGTHS = {"substantive", "definitional", "restatement", "stub", "alias"}

DECL = re.compile(
    r"^\s*(?:@\[[^\]]*\]\s*)*"
    r"(?:private\s+|protected\s+|noncomputable\s+)?"
    r"(?:def|theorem|lemma|abbrev|structure|inductive)\s+"
    r"([A-Za-z_][A-Za-z0-9_'.]*)"
)
NAMESPACE = re.compile(r"^namespace\s+([A-Za-z0-9_.]+)")
END = re.compile(r"^end\s+([A-Za-z0-9_.]+)")
INVARIANT_ID = re.compile(r"\b([IS]\d+)\b")
WEAK_BODY = re.compile(
    r"^(?:\(?\s*h\s*\)?|rfl|exact\s+\(?\s*h\s*\)?|"
    r"by\s+(?:simpa(?:\s*\[[^\]]*\])?\s+using\s+\(?\s*h\s*\)?|exact\s+\(?\s*h\s*\)?))$",
    re.S,
)


def load_register() -> dict:
    if not REGISTER.is_file():
        raise SystemExit(f"missing {REGISTER.relative_to(ROOT)}")
    data = yaml.safe_load(REGISTER.read_text())
    if data.get("schema") != "rcash.lean-claims/v1":
        raise SystemExit(f"{REGISTER.relative_to(ROOT)}: bad schema")
    return data


def lean_declarations() -> tuple[set[str], dict[str, str]]:
    """Return every declaration name and the body text of each theorem."""
    names: set[str] = set()
    bodies: dict[str, str] = {}
    for path in sorted(LEAN.rglob("*.lean")):
        text = path.read_text()
        namespaces: list[str] = []
        current: str | None = None
        chunk: list[str] = []
        depth = 0
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            match = NAMESPACE.match(stripped)
            if match:
                namespaces.extend(match.group(1).split("."))
                continue
            match = END.match(stripped)
            if match:
                for _ in match.group(1).split("."):
                    if namespaces:
                        namespaces.pop()
                continue
            match = DECL.match(stripped)
            if match and depth == 0:
                if current is not None:
                    bodies[current] = "\n".join(chunk)
                name = ".".join([*namespaces, match.group(1)])
                names.add(name)
                current = name if stripped.startswith(("theorem", "lemma")) else None
                chunk = [line]
                depth += line.count("{") - line.count("}")
                continue
            if current is not None:
                chunk.append(line)
                depth += line.count("{") - line.count("}")
                if depth <= 0 and stripped and not stripped.startswith(("|", "where")):
                    # A blank line at depth 0 ends the declaration chunk.
                    if line and not line[0].isspace():
                        bodies[current] = "\n".join(chunk)
                        current = None
                        chunk = []
        if current is not None:
            bodies[current] = "\n".join(chunk)
    return names, bodies


def body_term(body: str) -> str:
    """Extract the term after the last `:=` in a declaration body."""
    marker = body.rfind(":=")
    if marker < 0:
        return ""
    return body[marker + 2:].strip()


def required_invariants() -> set[str]:
    text = INVARIANTS.read_text()
    return set(re.findall(r"^\|\s*([IS]\d+)\s*\|", text, re.M))


def flow_invariants() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted(FLOWS.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        ids: set[str] = set()
        values = doc.get("invariants") or {}
        if isinstance(values, dict):
            ids.update(str(key) for key in values)
        elif isinstance(values, list):
            ids.update(str(item) for item in values)
        for component in doc.get("components", []):
            for arm in component.get("arms") or []:
                for item in arm.get("invariants") or []:
                    ids.update(INVARIANT_ID.findall(str(item)))
        if ids:
            found[path.name] = ids
    return found


def audit_names() -> set[str]:
    if not AUDIT.is_file():
        return set()
    return {
        name.strip()
        for name in re.findall(r"#print axioms\s+([A-Za-z0-9_.]+)", AUDIT.read_text())
    }


def declarations_of(entry: dict) -> list[dict]:
    return entry.get("theorems") or []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--strict-audit", action="store_true")
    args = parser.parse_args()

    register = load_register()
    names, bodies = lean_declarations()
    required = required_invariants()
    audited = audit_names()

    errors: list[str] = []
    warnings: list[str] = []

    claims = register.get("invariants") or {}
    missing = sorted(required - set(claims))
    extra = sorted(set(claims) - required)
    for inv in missing:
        errors.append(f"invariant {inv}: no entry in claims.yaml")
    for inv in extra:
        errors.append(f"invariant {inv}: entry is not in 20-INVARIANTS.md")

    status_counts: dict[str, int] = {status: 0 for status in STATUSES}
    substantive = 0
    weak: list[str] = []
    unaudited: list[str] = []

    def check_section(section: str, entries: dict) -> None:
        nonlocal substantive
        for key, entry in sorted(entries.items()):
            label = f"{section} {key}"
            status = entry.get("status")
            if status not in STATUSES:
                errors.append(f"{label}: unknown status {status!r}")
                continue
            status_counts[status] += 1
            if status == "deferred":
                if not entry.get("deferral"):
                    errors.append(f"{label}: deferred without a deferral record")
                if declarations_of(entry):
                    warnings.append(f"{label}: deferred but cites theorems")
                continue
            if status == "tool":
                if not entry.get("tool"):
                    errors.append(f"{label}: tool status without a tool name")
                continue
            if status == "partial" and not entry.get("note"):
                warnings.append(f"{label}: partial without a note")
            if not declarations_of(entry):
                errors.append(f"{label}: {status} but cites no theorem")

            substantive_here = 0
            for theorem in declarations_of(entry):
                name = theorem.get("name")
                strength = theorem.get("strength")
                if strength not in STRENGTHS:
                    errors.append(f"{label}: {name}: unknown strength {strength!r}")
                    continue
                if name not in names:
                    errors.append(f"{label}: {name} does not resolve in spec/lean")
                    continue
                if strength == "substantive":
                    substantive_here += 1
                    substantive += 1
                    term = body_term(bodies.get(name, ""))
                    if term and WEAK_BODY.match(term):
                        errors.append(
                            f"{label}: {name} is declared substantive but its body is a "
                            f"hypothesis restatement: {term.splitlines()[0][:60]!r}"
                        )
                else:
                    weak.append(f"{label}: {name} ({strength})")
                if name not in audited:
                    unaudited.append(f"{label}: {name}")
            if status == "covered" and substantive_here == 0:
                errors.append(f"{label}: covered but has no substantive theorem")

    check_section("invariant", claims)
    check_section("primitive", register.get("primitives") or {})

    for filename, ids in sorted(flow_invariants().items()):
        for inv in sorted(ids):
            if inv not in claims:
                errors.append(f"{filename}: invariant {inv} has no claim")

    if args.strict_audit:
        for item in unaudited:
            errors.append(f"not in Audit.lean: {item}")
    else:
        for item in unaudited:
            warnings.append(f"not in Audit.lean: {item}")

    print(
        "claims: "
        + ", ".join(f"{status}={status_counts[status]}" for status in sorted(STATUSES))
        + f", substantive={substantive}, weak={len(weak)}, unaudited={len(unaudited)}"
    )
    assumptions = register.get("assumptions") or {}
    if assumptions:
        print("assumptions: " + ", ".join(sorted(assumptions)))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)

    if errors and args.check:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
