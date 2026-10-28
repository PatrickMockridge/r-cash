#!/usr/bin/env python3
"""Strict consistency checks between the flow YAML, the deploy source and Lean.

    python3 tools/check_flows.py --report          # human report, always exit 0
    python3 tools/check_flows.py --check --strict   # gate

The checks are structural, not textual: the arm inventory is regenerated from
the deploy sources, helpers are expanded into their caller's access set, and
take/refusal/post order is read from positioned events.  That is what makes the
checker reject the D1/D2/D3 class rather than merely noticing that an arm was
forgotten.

Exit status is 1 in --check mode when an error is present.  --report prints the
same findings and returns 0, so it can be run while a subsystem is still being
written.
"""

from __future__ import annotations

import argparse
import json
import sys

import yaml
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import flowlib

LEAN_ROOT = flowlib.ROOT / "spec" / "lean"
MODEL_REGISTRY = flowlib.ROOT / "docs" / "spec" / "model.yaml"
VECTORS = flowlib.ROOT / "tests" / "vectors" / "arith.json"
MODEL_REQUIRED = {
    'CurrencyRegistry@"registerExternal"', 'CurrencyRegistry@"setPaused"',
    'MarketIndex@"pauseAsset"', 'MarketIndex@"stage"', 'MarketIndex@"marketFor"',
    'ListingViews@"marketFor"',
}


@dataclass
class Finding:
    check: str
    severity: str  # "error" | "warning" | "info"
    message: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, check: str, severity: str, message: str) -> None:
        self.findings.append(Finding(check, severity, message))

    def error(self, check: str, message: str) -> None:
        self.add(check, "error", message)

    def warn(self, check: str, message: str) -> None:
        self.add(check, "warning", message)

    def counts(self) -> tuple[int, int]:
        errors = sum(1 for f in self.findings if f.severity == "error")
        warnings = sum(1 for f in self.findings if f.severity == "warning")
        return errors, warnings

    def show(self, strict: bool) -> None:
        order = {"error": 0, "warning": 1, "info": 2}
        for finding in sorted(self.findings, key=lambda f: (order[f.severity], f.check)):
            print(f"{finding.severity.upper():7s} [{finding.check}] {finding.message}")
        errors, warnings = self.counts()
        print(f"\nflows: {errors} error(s), {warnings} warning(s)")
        if strict:
            print("mode: strict (verified or named blocked only)")


# ---------------------------------------------------------------------------
# Source model


class Source:
    def __init__(self, inventory: dict):
        self.inventory = inventory
        self.arms = {node["key"]: node for node in inventory["arms"]}
        self.helpers = {node["key"]: node for node in inventory["helpers"]}
        self.state_cells = set(inventory["state_cells"])

    def expand(self, node: dict) -> list[tuple[str, dict]]:
        """The node plus every helper it calls, transitively.

        Returns (origin, node) pairs.  ``origin`` is ``arm`` for the arm body
        and ``helper:<name>`` for a helper reached directly from the arm.
        """
        result = [("arm", node)]
        seen = {node["key"]}
        frontier = [(f"helper:{name}", self.helpers[name]) for name in node["sends"]
                    if name in self.helpers]
        while frontier:
            origin, helper = frontier.pop(0)
            if helper["key"] in seen:
                continue
            seen.add(helper["key"])
            result.append((origin, helper))
            for name in helper["sends"]:
                if name in self.helpers and name not in seen:
                    frontier.append((f"helper:{helper['key']}", self.helpers[name]))
        return result

    def access(self, node: dict) -> tuple[dict[str, set[str]], dict[tuple[str, str], set[str]]]:
        """Union access and per-(mode,cell) origin attribution."""
        union = {"peek": set(), "consume": set(), "post": set()}
        origin: dict[tuple[str, str], set[str]] = {}
        for who, part in self.expand(node):
            for event in part["events"]:
                mode = {"peek": "peek", "take": "consume", "post": "post"}[event["kind"]]
                union[mode].add(event["cell"])
                origin.setdefault((mode, event["cell"]), set()).add(who)
        return union, origin

    def refusal_reasons(self, node: dict) -> set[str]:
        reasons: set[str] = set()
        for _, part in self.expand(node):
            reasons.update(hit["reason"] for hit in part["refusal_hits"])
        return reasons

    @staticmethod
    def _prefix(inner: list, outer: list) -> bool:
        return len(inner) <= len(outer) and all(a == b for a, b in zip(inner, outer))

    def after_consume(self, node: dict) -> list[tuple[str, str, str, int, list]]:
        """(cell, reason, line) for every refusal that is reached while a take
        of that cell is live on the same branch path.

        A take in one arm of an `if`/`match` is not live in the sibling arm, so
        only takes whose path prefixes the refusal path count.
        """
        events: list[tuple[str, int, int, str, str, list]] = []
        refusals: list[tuple[str, int, str, list]] = []
        for _, part in self.expand(node):
            for event in part["events"]:
                events.append((part["file"], event["line"], 0, event["kind"],
                               event["cell"], event["path"]))
            for refusal in part["refusal_hits"]:
                refusals.append((part["file"], refusal["line"], refusal["reason"],
                                 refusal["path"]))
        found: list[tuple[str, str, str, int, list]] = []
        for file, line, reason, path in refusals:
            for cell in {e[4] for e in events if e[0] == file}:
                takes = [e for e in events
                         if e[0] == file and e[4] == cell and e[3] == "take"
                         and e[1] <= line and self._prefix(e[5], path)]
                if not takes:
                    continue
                take_line = max(e[1] for e in takes)
                reposted = any(
                    e[0] == file and e[4] == cell and e[3] == "post"
                    and take_line <= e[1] <= line and self._prefix(e[5], path)
                    for e in events)
                if not reposted:
                    found.append((file, cell, reason, line, path))
        unique = {(file, cell, reason, line, tuple(tuple(p) for p in path))
                  for file, cell, reason, line, path in found}
        return sorted(
            [(file, cell, reason, line, [list(p) for p in path])
             for file, cell, reason, line, path in unique],
            key=lambda item: (item[3], item[1], item[2]))

    def fail_on_path(self, node: dict, file: str, line: int, path: list) -> bool:
        for _, part in self.expand(node):
            if part["file"] != file:
                continue
            for fail in part["fail_hits"]:
                if fail["line"] >= line and self._prefix(fail["path"], path):
                    return True
        return False

    def peek_then_post(self, node: dict) -> list[tuple[str, int, int]]:
        """Posts whose most recent access of the same cell on the same branch
        path was a peek (or nothing): a duplicate cell.
        """
        problems: list[tuple[str, int, int]] = []
        for origin, part in self.expand(node):
            events = sorted(part["events"], key=lambda e: e["line"])
            for post in events:
                if post["kind"] != "post":
                    continue
                previous = [
                    e for e in events
                    if e["cell"] == post["cell"] and e["line"] <= post["line"]
                    and self._prefix(e["path"], post["path"])
                    and not (e is post)
                ]
                if previous:
                    last = max(previous, key=lambda e: e["line"])
                    if last["kind"] == "peek":
                        problems.append((post["cell"], last["line"], post["line"]))
                elif post["cell"] in part.get("fresh", []):
                    continue  # initialisation of a cell created in this body
                elif origin == "arm":
                    problems.append((post["cell"], 0, post["line"]))
        return problems


# ---------------------------------------------------------------------------


def covered_source(patterns: list[str]) -> set[str]:
    files: set[str] = set()
    for pattern in patterns:
        for path in flowlib.ROOT.glob(pattern):
            if path.is_file():
                files.add(str(path.relative_to(flowlib.ROOT)))
    return files


def check_models(arm: dict, where: str, report: Report) -> None:
    models = {}
    if MODEL_REGISTRY.is_file():
        models = yaml.safe_load(MODEL_REGISTRY.read_text()).get("transitions") or {}
    name = arm.get("arm")
    if name in MODEL_REQUIRED and not arm.get("model"):
        report.error("model", f"{where}: requires a model transition")
    if arm.get("model"):
        if arm["model"] not in models:
            report.error("model", f"{where}: model {arm['model']!r} is not registered")
        else:
            artifact = flowlib.ROOT / (models[arm["model"]].get("test") or "")
            if models[arm["model"]].get("test") and not artifact.exists():
                report.error("model", f"{where}: model test {artifact} is missing")
    if arm.get("vector"):
        vectors = {}
        if VECTORS.is_file():
            vectors = json.loads(VECTORS.read_text())
        if arm["vector"] not in vectors:
            report.error("vector", f"{where}: vector {arm['vector']!r} is missing")


def check_documents(docs: list[dict], source: Source, report: Report,
                    strict: bool) -> None:
    catalogue = flowlib.refusal_catalogue()
    lean = flowlib.lean_names(LEAN_ROOT)
    seen_arms: dict[str, str] = {}
    seen_files: Counter[str] = Counter()
    mutating_lean: set[str] = set()

    for doc in docs:
        subsystem = doc.get("subsystem", doc["_path"].stem)
        globs = doc.get("source_globs") or []
        files = covered_source(globs)
        if not globs and not doc.get("components"):
            continue  # a normative-only document such as 00-cell.yaml
        if not files:
            report.error("coverage", f"{subsystem}: source_globs match no file")
        for path in files:
            seen_files[path] += 1

        for component in doc.get("components", []):
            cname = component.get("name", "?")
            for arm in component.get("arms", []):
                key = arm.get("arm")
                where = f"{subsystem}/{cname}/{key}"
                if not key:
                    report.error("schema", f"{where}: missing arm")
                    continue
                if key in seen_arms:
                    report.error("duplicate", f"{key} appears in {seen_arms[key]} and {where}")
                seen_arms[key] = where

                node = source.arms.get(key)
                if node is None:
                    report.error("coverage", f"{where}: no such arm in the deploy source")
                    continue

                # 2. source line
                src = arm.get("source") or {}
                if src.get("file") != node["file"]:
                    report.error("source", f"{where}: file {src.get('file')} != {node['file']}")
                if src.get("line") != node["line"]:
                    report.error("source", f"{where}: line {src.get('line')} != {node['line']}")

                check_models(arm, where, report)

                # 10. honesty about mutation
                own_mutates = bool(node["events"]) and any(
                    e["kind"] == "post" for e in node["events"])
                expanded = source.expand(node)
                declared = any(
                    '@"' in (call.get("callee") or "")
                    for call in arm.get("nested_calls") or [])
                any_mutates = declared or any(
                    e["kind"] == "post" for _, part in expanded for e in part["events"])
                kind = arm.get("kind")
                if kind == "read" and any_mutates:
                    report.error("honesty", f"{where}: marks a mutating arm as read")
                if kind == "mutate" and not any_mutates:
                    report.error("honesty", f"{where}: marks a non-mutating arm as mutate")
                if kind not in flowlib.KINDS:
                    report.error("schema", f"{where}: unknown kind {kind!r}")
                if kind == "mutate":
                    delegation = bool(arm.get("effects")) and all(
                        item.get("target") == "delegate" for item in arm["effects"])
                    if not arm.get("guards") and not delegation:
                        report.error("schema", f"{where}: mutating arm has no guards")
                    if not arm.get("effects"):
                        report.error("schema", f"{where}: mutating arm has no effects")
                    if arm.get("lean"):
                        mutating_lean.add(arm["lean"])

                # 3. access and actor attribution
                union, origin = source.access(node)
                yml = flowlib.flatten_access(arm)
                for mode in ("peek", "consume", "post"):
                    missing = union[mode] - yml[mode]
                    extra = yml[mode] - union[mode]
                    for cell in sorted(missing):
                        report.error("access", f"{where}: source {mode}s {cell}, YAML omits it")
                    for cell in sorted(extra):
                        report.error("access", f"{where}: YAML {mode}s {cell}, source does not")
                for mode in ("peek", "consume", "post"):
                    for entry in arm.get("access") or []:
                        if entry.get("mode") != mode:
                            continue
                        cell = entry.get("cell")
                        expected = origin.get((mode, cell))
                        if not expected:
                            continue
                        actor = entry.get("actor", "arm")
                        if actor not in expected:
                            report.error(
                                "actor",
                                f"{where}: {mode} {cell} attributed to {actor}, "
                                f"source says {sorted(expected)}")

                # 4. refusal taxonomy
                yml_reasons = {r.get("reason") for r in arm.get("refusals", []) if r.get("reason")}
                src_reasons = source.refusal_reasons(node)
                for reason in sorted(src_reasons - yml_reasons):
                    report.error("refusal", f"{where}: source refusal {reason!r} is not in YAML")
                for reason in sorted(yml_reasons - src_reasons):
                    report.error("refusal", f"{where}: YAML refusal {reason!r} is not in source")
                for reason in sorted(yml_reasons):
                    if reason not in catalogue:
                        report.warn("catalogue", f"{where}: refusal {reason!r} absent from SPEC §18.3")

                # 5. after-consume purity, from source path/branch order
                source_after = source.after_consume(node)
                yml_refusals = arm.get("refusals") or []
                for file, cell, reason, line, path in source_after:
                    matches = [r for r in yml_refusals if r.get("reason") == reason]
                    if not matches:
                        continue  # already reported by check 4
                    if not any(r.get("phase") == "after_consume" for r in matches):
                        report.error(
                            "cell",
                            f"{where}: refusal {reason!r} at line {line} follows a take of "
                            f"{cell} but is not annotated after_consume")
                    for r in matches:
                        if r.get("phase") != "after_consume":
                            continue
                        if not (r.get("reposts") or r.get("fail")):
                            report.error(
                                "cell",
                                f"{where}: model refusal {reason!r} after taking {cell} has "
                                f"neither reposts nor fail")
                        elif r.get("fail") and not source.fail_on_path(node, file, line, path):
                            report.error(
                                "cell",
                                f"{where}: model refusal {reason!r} says fail, but the source "
                                f"refusal at line {line} returns a reply (not 1/0)")
                        elif r.get("reposts"):
                            report.error(
                                "cell",
                                f"{where}: model requires a repost of {cell} before refusal "
                                f"{reason!r}, but the source refusal at line {line} loses the "
                                f"cell (status {arm.get('status')})")
                annotated = {r.get("reason") for r in yml_refusals
                             if r.get("phase") == "after_consume"}
                for reason in annotated - {r[2] for r in source_after}:
                    entries = [r for r in yml_refusals if r.get("reason") == reason
                               and r.get("phase") == "after_consume"]
                    if entries and all(r.get("reposts") or r.get("fail") for r in entries):
                        # The source took the cell and reposted it before this
                        # refusal; the arm is clean, not a lost cell.
                        continue
                    report.warn(
                        "cell",
                        f"{where}: {reason!r} claims after_consume but no live take precedes it")

                # 6. peek-then-post / post-without-take
                for cell, peek_line, post_line in source.peek_then_post(node):
                    if peek_line:
                        report.error(
                            "cell",
                            f"{where}: {cell} peeked at {peek_line} then posted at {post_line} "
                            f"without a take (duplicate cell)")
                    else:
                        report.error(
                            "cell",
                            f"{where}: {cell} posted at {post_line} with no take (duplicate cell)")

                # 7. helper protocol / token continuity
                nested = {call.get("callee"): call for call in arm.get("nested_calls") or []}
                direct_helpers = [name for name in node["sends"] if name in source.helpers]
                for name in direct_helpers:
                    call = nested.get(name)
                    if call is None:
                        report.error(
                            "protocol", f"{where}: calls helper {name} without a nested_calls entry")
                        continue
                    protocol = call.get("protocol")
                    if protocol not in flowlib.PROTOCOLS:
                        report.error("protocol", f"{where}: {name} has unknown protocol {protocol!r}")
                    helper = source.helpers[name]
                    takes = {e["cell"] for e in helper["events"] if e["kind"] == "take"}
                    posts = {e["cell"] for e in helper["events"] if e["kind"] == "post"}
                    if protocol == "H2b":
                        missing = (takes - set(call.get("takes", []))) | (
                            posts - set(call.get("puts", [])))
                        if missing:
                            report.error(
                                "protocol",
                                f"{where}: H2b {name} takes/puts {sorted(missing)} not declared")
                        if call.get("post_owner") != "helper":
                            report.error("protocol", f"{where}: H2b {name} must set post_owner helper")
                    elif protocol == "H2a":
                        if call.get("post_owner") != "helper":
                            report.error("protocol", f"{where}: H2a {name} must set post_owner helper")
                        arm_takes = {e["cell"] for e in node["events"] if e["kind"] == "take"}
                        if posts - arm_takes:
                            report.error(
                                "protocol",
                                f"{where}: H2a {name} posts {sorted(posts - arm_takes)} but the "
                                f"caller does not hold them")
                    elif protocol == "P3":
                        creates = set(call.get("creates") or [])
                        if posts - creates:
                            report.error(
                                "protocol",
                                f"{where}: P3 {name} posts {sorted(posts - creates)} it does not create")
                        if creates - set(helper.get("fresh") or []):
                            report.error(
                                "protocol",
                                f"{where}: P3 {name} creates {sorted(creates)} not bound in its body")
                    elif protocol in ("P0", "H1"):
                        if takes or posts:
                            report.error(
                                "protocol",
                                f"{where}: {protocol} helper {name} touches state {sorted(takes | posts)}")

                # 8. Lean declaration
                lean_name = arm.get("lean")
                if not lean_name:
                    report.error("lean", f"{where}: missing lean declaration")
                elif lean and lean_name not in lean:
                    report.error("lean", f"{where}: Lean declaration {lean_name} not found")
                elif not lean:
                    report.warn("lean", f"{where}: no Lean project to check {lean_name}")

                # status
                status = arm.get("status")
                if status not in flowlib.STATUSES:
                    report.error("status", f"{where}: unknown status {status!r}")
                if strict:
                    if status not in ("verified", "blocked"):
                        report.error("status", f"{where}: status {status!r} in strict mode")
                    if status == "blocked" and not arm.get("blocked_reason"):
                        report.error("status", f"{where}: blocked without a named reason")

    # Coverage of the deploy source. A deploy file may be split across several
    # flow documents (the issuer file contributes four); an *arm* may not.
    all_sources = set(source.inventory["source"])
    for path in sorted(all_sources - set(seen_files)):
        report.error("coverage", f"{path}: no flow YAML covers this deploy file")
    missing_arms = set(source.arms) - set(seen_arms)
    for key in sorted(missing_arms):
        node = source.arms[key]
        report.error("coverage", f"{node['file']}:{node['line']}: {key} has no YAML transition")

    # 10. shadowed binders are never acceptable
    for node in source.inventory["arms"] + source.inventory["helpers"]:
        if node["shadowed"]:
            report.error(
                "binder",
                f"{node['file']}:{node['line']}: {node['key']} shadows {node['shadowed']}")

    # Duplicate source arms are an inventory error
    for duplicate in source.inventory["duplicates"]:
        report.error("duplicate", duplicate)

    # Every Lean transition declared by a mutating arm must be a `def`/`theorem`
    # in the project; the reverse direction is checked by the Lean build, which
    # fails on an unreferenced theorem only if it is stated as a required audit.
    if lean:
        for name in sorted(mutating_lean - lean):
            report.error("lean", f"mutating transition {name} has no Lean declaration")


def check_mesh_gate(report: Report) -> None:
    import subprocess
    proc = subprocess.run([sys.executable, str(flowlib.ROOT / "tools" / "check_mesh.py")],
                          text=True, capture_output=True)
    if proc.returncode != 0:
        for line in (proc.stderr or proc.stdout).splitlines():
            report.error("mesh", line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    source = Source(flowlib.inventory())
    docs = flowlib.documents()
    report = Report()
    if not docs:
        report.error("coverage", "no flow YAML documents")
    check_documents(docs, source, report, args.strict)
    check_mesh_gate(report)
    report.show(args.strict)
    if args.check and report.counts()[0]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
