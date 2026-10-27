"""Shared loading for the flow specification tools."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FLOWS = ROOT / "docs" / "spec" / "flows"
SPEC = ROOT / "docs" / "SPEC.md"

SCHEMA = "rcash.flows/v1"
STATUSES = {"unreconciled", "fixed", "verified", "blocked"}
KINDS = {"mutate", "read", "create", "helper"}
PROTOCOLS = {"P0", "P1", "P2", "P3", "P4", "P5", "P6", "H1", "H2a", "H2b"}
MODES = {"peek", "consume", "post"}


def documents() -> list[dict]:
    out = []
    for path in sorted(FLOWS.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        if not isinstance(doc, dict):
            raise SystemExit(f"{path}: not a mapping")
        doc["_path"] = path
        out.append(doc)
    return out


def arms(docs: list[dict]):
    for doc in docs:
        for component in doc.get("components", []):
            for arm in component.get("arms") or []:
                yield doc, component, arm


def arm_key(component: dict, arm: dict) -> str:
    return arm.get("arm") or f'{component.get("name")}@"?"'


def refusal_catalogue() -> set[str]:
    """Parse the fenced refusal list under SPEC §18.3."""
    text = SPEC.read_text()
    marker = "### 18.3 Refusal strings"
    start = text.index(marker)
    fence = text.index("```", start)
    end = text.index("```", fence + 3)
    block = text[fence + 3:end]
    phrases: set[str] = set()
    for line in block.splitlines():
        for part in re.split(r"\s{2,}", line.strip()):
            part = part.strip()
            if part:
                phrases.add(part)
    return phrases


def inventory() -> dict:
    import rho_inventory

    return rho_inventory.inventory()


def flatten_access(arm: dict) -> dict[str, set[str]]:
    out = {mode: set() for mode in ("peek", "consume", "post")}
    for entry in arm.get("access") or []:
        mode = entry.get("mode")
        cell = entry.get("cell")
        if mode in MODES and cell:
            out[mode].add(cell)
    return out


def after_consume_unclean(arm: dict) -> list[dict]:
    bad = []
    for refusal in arm.get("refusals") or []:
        if refusal.get("phase") == "after_consume":
            if not (refusal.get("reposts") or refusal.get("fail")):
                bad.append(refusal)
    return bad


def lean_names(root: Path) -> set[str]:
    """Fully qualified `def`/`theorem` names with namespace tracking."""
    names: set[str] = set()
    if not root.is_dir():
        return names
    for path in root.rglob("*.lean"):
        namespaces: list[str] = []
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            match = re.match(r"namespace\s+([A-Za-z0-9_.]+)", stripped)
            if match:
                namespaces.extend(match.group(1).split("."))
                continue
            match = re.match(r"end\s+([A-Za-z0-9_.]+)", stripped)
            if match:
                parts = match.group(1).split(".")
                for _ in parts:
                    if namespaces:
                        namespaces.pop()
                continue
            match = re.match(
                r"(?:private\s+|protected\s+|noncomputable\s+)?"
                r"(?:def|theorem|lemma|abbrev|structure|inductive)\s+"
                r"([A-Za-z_][A-Za-z0-9_'.]*)",
                stripped,
            )
            if match:
                names.add(".".join([*namespaces, match.group(1)]))
    return names
