#!/usr/bin/env python3
"""Render the flow YAML into Mermaid diagrams, tables and the traceability matrix.

    python3 tools/render_flows.py            # write the .md files
    python3 tools/render_flows.py --check    # fail if any generated file is stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import flowlib


def esc(value) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def bullet(items) -> str:
    if not items:
        return "—"
    return "<br>".join(esc(item) for item in items)


def diagram(component: dict) -> list[str]:
    name = component.get("name", "Component")
    states = component.get("states") or ["Ready"]
    initial = component.get("initial") or states[0]
    lines = [f"### {name}", "", "```mermaid", "stateDiagram-v2"]
    if initial in states:
        lines.append(f"  [*] --> {initial}")
    destroyed = False
    for arm in component.get("arms", []):
        transition = arm.get("transition", arm.get("arm", "?"))
        source = arm.get("from") or initial
        target = arm.get("to") or source
        label = f"{transition}"
        reason = arm.get("on") or ""
        if reason:
            label += f": {reason}"
        lines.append(f"  {source} --> {target}: {label}")
        for refusal in arm.get("refusals", []):
            if refusal.get("state"):
                lines.append(
                    f"  {source} --> {refusal['state']}: {refusal.get('reason', 'refused')}"
                )
        if flowlib.after_consume_unclean(arm):
            destroyed = True
    if destroyed:
        lines += ["  state CellDestroyed", "  %% DEFECT: a graceful refusal after a take"]
    lines += ["```", ""]
    return lines


def component_table(component: dict) -> list[str]:
    lines = [
        f"#### {component.get('name', 'Component')} arms",
        "",
        "| arm | transition | kind | guards | effects | access | refusals | invariants | status | source |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in component.get("arms", []):
        guards = [
            f"{g.get('expr', '?')} → {g.get('refusal', {}).get('reason', 'refuse')}"
            for g in arm.get("guards", [])
        ]
        effects = [
            f"{e.get('target', '?')} = {e.get('formula', '?')}"
            for e in arm.get("effects", [])
        ]
        access = [
            f"{a.get('mode', '?')} {a.get('cell', '?')} ({a.get('actor', 'arm')})"
            for a in arm.get("access", [])
        ]
        refusals = [
            f"{r.get('reason', '?')} ({r.get('phase', '?')}"
            f"{', repost' if r.get('reposts') else ''}"
            f"{', fail' if r.get('fail') else ''})"
            for r in arm.get("refusals", [])
        ]
        source = arm.get("source", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{esc(arm.get('arm', '?'))}`",
                    f"`{esc(arm.get('transition', '?'))}`",
                    esc(arm.get("kind", "?")),
                    bullet(guards),
                    bullet(effects),
                    bullet(access),
                    bullet(refusals),
                    bullet(arm.get("invariants", [])),
                    esc(arm.get("status", "?")),
                    esc(f"{source.get('file', '?')}:{source.get('line', '?')}"),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def rules_table(doc: dict) -> list[str]:
    lines: list[str] = []
    if doc.get("rules"):
        lines += ["| rule | name | statement | rejects | Lean |",
                  "|---|---|---|---|---|"]
        for rule in doc["rules"]:
            lines.append(
                "| "
                + " | ".join([
                    f"`{esc(rule.get('id'))}`",
                    esc(rule.get("name")),
                    esc(rule.get("rule")),
                    esc(", ".join(rule.get("rejects") or [])),
                    f"`{esc(rule.get('lean'))}`" if rule.get("lean") else "—",
                ])
                + " |")
        lines.append("")
    if doc.get("protocols"):
        lines += ["| protocol | meaning |", "|---|---|"]
        for protocol in doc["protocols"]:
            lines.append(f"| `{esc(protocol.get('label'))}` | {esc(protocol.get('meaning'))} |")
        lines.append("")
    if doc.get("helpers"):
        lines += ["| helper class | rule |", "|---|---|"]
        for helper in doc["helpers"]:
            lines.append(f"| `{esc(helper.get('class'))}` | {esc(helper.get('rule'))} |")
        lines.append("")
    return lines


def lifecycle_table(doc: dict) -> list[str]:
    lines: list[str] = []
    if doc.get("states") and doc.get("transitions"):
        lines += ["## Lifecycle", "", "```mermaid", "stateDiagram-v2",
                  f"  [*] --> {doc.get('initial', doc['states'][0])}"]
        for transition in doc["transitions"]:
            label = transition.get("id", "transition")
            trigger = transition.get("trigger")
            if trigger:
                label += f": {trigger}"
            lines.append(f"  {transition['from']} --> {transition['to']}: {label}")
        lines += ["```", ""]
        lines += ["| transition | from | to | trigger | requirement |",
                  "|---|---|---|---|---|"]
        for transition in doc["transitions"]:
            lines.append("| " + " | ".join([
                f"`{esc(transition.get('id'))}`",
                esc(transition.get("from")),
                esc(transition.get("to")),
                esc(transition.get("trigger")),
                f"`{esc(transition.get('requirement'))}`",
            ]) + " |")
        lines.append("")
    if doc.get("refusals"):
        lines += ["| refusal | reason | requirement |", "|---|---|---|"]
        for refusal in doc["refusals"]:
            lines.append("| " + " | ".join([
                f"`{esc(refusal.get('id'))}`",
                f"`{esc(refusal.get('reason'))}`",
                f"`{esc(refusal.get('requirement'))}`",
            ]) + " |")
        lines.append("")
    if doc.get("client_flows"):
        lines += ["| client flow | given | when | then | requirement |",
                  "|---|---|---|---|---|"]
        for flow in doc["client_flows"]:
            lines.append("| " + " | ".join([
                f"`{esc(flow.get('id'))}`",
                esc(flow.get("given")),
                esc(flow.get("when")),
                esc(flow.get("then")),
                f"`{esc(flow.get('requirement'))}`",
            ]) + " |")
        lines.append("")
    return lines


def render_document(doc: dict) -> str:
    title = doc.get("subsystem", doc["_path"].stem)
    lines = [
        f"<!-- GENERATED by tools/render_flows.py from {doc['_path'].name}; do not edit -->",
        "",
        f"# Flow: {title}",
        "",
        f"Schema: `{doc.get('schema', flowlib.SCHEMA)}`",
    ]
    if doc.get("source_globs"):
        lines.append("Source: " + ", ".join(f"`{s}`" for s in doc["source_globs"]))
    lines.append("")
    lines += lifecycle_table(doc)
    lines += rules_table(doc)
    invariants = doc.get("invariants", {})
    if invariants:
        lines += ["| invariant | statement | Lean |", "|---|---|---|"]
        for key, value in invariants.items():
            if isinstance(value, dict):
                lines.append(
                    f"| {esc(key)} | {esc(value.get('statement'))} | `{esc(value.get('lean'))}` |"
                )
        lines.append("")
    for component in doc.get("components", []):
        lines += diagram(component)
        lines += component_table(component)
    return "\n".join(lines).rstrip() + "\n"


def render_traceability(docs: list[dict]) -> str:
    lines = [
        "<!-- GENERATED by tools/render_flows.py; do not edit -->",
        "",
        "# Traceability: contract arm → transition → Lean → source",
        "",
        "| arm | subsystem | transition | Lean | kind | status | source |",
        "|---|---|---|---|---|---|---|",
    ]
    for doc, component, arm in flowlib.arms(docs):
        source = arm.get("source", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{esc(flowlib.arm_key(component, arm))}`",
                    esc(doc.get("subsystem", doc["_path"].stem)),
                    f"`{esc(arm.get('transition', '?'))}`",
                    f"`{esc(arm.get('lean', '?'))}`",
                    esc(arm.get("kind", "?")),
                    esc(arm.get("status", "?")),
                    esc(f"{source.get('file', '?')}:{source.get('line', '?')}"),
                ]
            )
            + " |"
        )
    return "\n".join(lines).rstrip() + "\n"


def render_reconciliation(docs: list[dict]) -> str:
    lines = [
        "<!-- GENERATED by tools/render_flows.py; do not edit -->",
        "",
        "# Reconciliation",
        "",
        "## Defect register",
        "",
        "| ID | arm / subject | defect | required fix | status |",
        "|---|---|---|---|---|",
    ]
    for doc in docs:
        for defect in doc.get("defects", []):
            lines.append(
                "| "
                + " | ".join(
                    esc(defect.get(k, ""))
                    for k in ("id", "subject", "defect", "fix", "status")
                )
                + " |"
            )
    lines += [
        "",
        "## Per-arm checklist",
        "",
        "| arm | transition | access modes | after-consume purity | effects | Lean | status | blocker / fix |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for doc, component, arm in flowlib.arms(docs):
        modes = ", ".join(
            f"{m}:{len(cells)}" for m, cells in flowlib.flatten_access(arm).items() if cells
        ) or "—"
        unclean = flowlib.after_consume_unclean(arm)
        purity = "OK" if not unclean else "DEFECT: " + ", ".join(
            r.get("reason", "?") for r in unclean
        )
        effects = "yes" if arm.get("effects") else "—"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{esc(flowlib.arm_key(component, arm))}`",
                    f"`{esc(arm.get('transition', '?'))}`",
                    esc(modes),
                    esc(purity),
                    esc(effects),
                    f"`{esc(arm.get('lean', '?'))}`",
                    esc(arm.get("status", "?")),
                    esc(arm.get("blocked_reason") or arm.get("fix") or ""),
                ]
            )
            + " |"
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    docs = flowlib.documents()
    outputs: dict[Path, str] = {}
    for doc in docs:
        outputs[doc["_path"].with_suffix(".md")] = render_document(doc)
    outputs[flowlib.FLOWS / "TRACEABILITY.md"] = render_traceability(docs)
    outputs[flowlib.FLOWS / "RECONCILIATION.md"] = render_reconciliation(docs)
    stale = []
    for path, text in outputs.items():
        if args.check:
            if not path.is_file() or path.read_text() != text:
                stale.append(path)
        else:
            path.write_text(text)
    if args.check:
        for path in stale:
            print(f"stale generated flow: {path.relative_to(flowlib.ROOT)}", file=sys.stderr)
        if stale:
            return 1
        print(f"flows: generated files up to date ({len(docs)} subsystems)")
        return 0
    print(f"flows: wrote {len(outputs)} generated files from {len(docs)} subsystems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
