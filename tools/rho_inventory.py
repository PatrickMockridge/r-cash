#!/usr/bin/env python3
"""Generate the Rholang arm/helper inventory from the deploy sources.

The flow specification must cover every arm and every helper. A hand-maintained
list drifts, so this tool derives the list from the source with a brace-matching
scope tree:

  * strip comments outside strings;
  * find `contract Name(...) = { ... }` blocks and their nesting;
  * an arm is a contract whose first formal is a literal (`@"op"`);
  * a helper is a contract with no literal first formal;
  * record every peek (`<<-`), consume (`<-`), post (`cell!`), refusal string,
    `1/0` path, send and `new` binder;
  * report a shadowed binder when a nested `new` rebinds an ancestor's name.

Only `contracts/src/deploy/**/*.rho` is in scope; the legacy `contracts/src/`
fragments are excluded explicitly.

Usage:
    python3 tools/rho_inventory.py            # print
    python3 tools/rho_inventory.py --write    # write contracts/build/arm_inventory.json
    python3 tools/rho_inventory.py --check    # fail if the committed file is stale
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "contracts" / "src" / "deploy"
OUT = ROOT / "contracts" / "build" / "arm_inventory.json"

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CONTRACT = re.compile(r"\bcontract\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
NEW = re.compile(r"\bnew\s+([^;]*?)\s+in\s*\{", re.S)
LITERAL_FIRST = re.compile(r'^\s*@?"([^"]+)"')
PEEK = re.compile(r"<<-\s*([A-Za-z_][A-Za-z0-9_]*)")
CONSUME = re.compile(r"(?<!<)<-\s*([A-Za-z_][A-Za-z0-9_]*)")
POST = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)!\(")
REFUSAL = re.compile(r'\(false,\s*"([^"]+)"')
FAIL = re.compile(r"1\s*/\s*0")
SEND_OP = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)!\("([^"]+)"')


@dataclass
class Node:
    name: str
    kind: str  # "arm" | "helper"
    op: str | None
    file: str
    line: int
    start: int
    body_start: int
    body_end: int
    parent: str | None
    nested: list[str] = field(default_factory=list)
    peeks: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    posts: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    refusal_hits: list[dict] = field(default_factory=list)
    fail_hits: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    fail_paths: int = 0
    sends: list[str] = field(default_factory=list)
    send_ops: list[str] = field(default_factory=list)
    binders: list[str] = field(default_factory=list)
    fresh: list[str] = field(default_factory=list)
    shadowed: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f'{self.name}@"{self.op}"' if self.op is not None else self.name


def strip_comments(text: str) -> str:
    """Blank out comments while preserving positions and newlines."""
    out: list[str] = []
    i = 0
    in_string = False
    escaped = False
    while i < len(text):
        c = text[i]
        if in_string:
            out.append(c)
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == "/" and i + 1 < len(text) and text[i + 1] == "*":
            while i < len(text) and not (text[i] == "*" and i + 1 < len(text) and text[i + 1] == "/"):
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i + 1 < len(text):
                out.extend([" ", " "])
                i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def matching(text: str, start: int, open_char: str, close_char: str) -> int:
    depth = 0
    in_string = False
    escaped = False
    i = start
    while i < len(text):
        c = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == open_char:
                depth += 1
            elif c == close_char:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise ValueError(f"unbalanced {open_char}{close_char} from {start}")


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


class BlockTree:
    """Brace blocks with an exclusive-branch index.

    A take is live at a refusal only when the take's branch path is a prefix of
    the refusal's: `if (c) { take } else { refuse }` are siblings, so the take
    is not held on the refusal path.  This is the smallest amount of control
    flow needed to keep the linear-cell check honest.
    """

    def __init__(self, text: str):
        self.text = text
        stack: list[int] = []
        self.parent: dict[int, int | None] = {}
        self.end: dict[int, int] = {}
        children: dict[int | None, list[int]] = {}
        for index, char in enumerate(text):
            if char == "{":
                self.parent[index] = stack[-1] if stack else None
                children.setdefault(self.parent[index], []).append(index)
                stack.append(index)
            elif char == "}" and stack:
                self.end[stack.pop()] = index
        self.branch: dict[int, int] = {}
        for parent, starts in children.items():
            branch_count = 0
            for start in starts:
                if self._is_branch(start):
                    self.branch[start] = branch_count
                    branch_count += 1
                else:
                    self.branch[start] = 0
        self.starts = sorted(self.parent)

    def _prefix(self, start: int, back: int = 160) -> str:
        return self.text[max(0, start - back):start].rstrip()

    def _is_branch(self, start: int) -> bool:
        prefix = self._prefix(start)
        if prefix.endswith("=>"):
            return True
        if re.search(r"\belse\s*$", prefix):
            return True
        # `if (...)` / `match (...) {`: the last structural keyword before the
        # brace is a test, and no closing brace intervenes.
        tail = prefix[-80:]
        if re.search(r"\b(if|match)\b", tail) and "}" not in tail:
            return True
        return False

    def path(self, pos: int) -> list[list[int]]:
        chain = []
        for start in self.starts:
            if start < pos <= self.end.get(start, -1):
                chain.append(start)
        return [[start, self.branch[start]] for start in chain]


def binder_names(binder_text: str) -> list[str]:
    names: list[str] = []
    for raw in binder_text.split(","):
        raw = raw.strip()
        if not raw:
            continue
        # `rl(`rho:registry:lookup`)`, `bd(...)`: the binder is the identifier before `(`.
        name = raw.split("(")[0].strip()
        if IDENT.fullmatch(name):
            names.append(name)
    return names


def collect_new_binders(text: str) -> list[tuple[int, int, list[str]]]:
    """(start, end, names) for every `new ... in { ... }` block."""
    result = []
    for match in NEW.finditer(text):
        try:
            end = matching(text, match.end() - 1, "{", "}")
        except ValueError:
            continue
        result.append((match.start(), end, binder_names(match.group(1))))
    return result


def enclosing_new(binders: list[tuple[int, int, list[str]]], pos: int) -> list[str]:
    names: list[str] = []
    for start, end, bound in binders:
        if start <= pos <= end:
            names.extend(bound)
    return names


def contract_nodes(text: str, file: str) -> list[Node]:
    nodes: list[Node] = []
    binders = collect_new_binders(text)
    blocks = BlockTree(text)
    stack: list[tuple[int, Node]] = []  # (body_end, node)
    for match in CONTRACT.finditer(text):
        name = match.group(1)
        try:
            close_paren = matching(text, match.end() - 1, "(", ")")
        except ValueError:
            continue
        params = text[match.end():close_paren]
        eq = text.find("=", close_paren)
        if eq == -1:
            continue
        brace = text.find("{", eq)
        if brace == -1:
            continue
        try:
            body_end = matching(text, brace, "{", "}")
        except ValueError:
            continue
        first = params.split(",", 1)[0]
        literal = LITERAL_FIRST.search(first)
        op = literal.group(1) if literal else None
        node = Node(
            name=name,
            kind="arm" if op is not None else "helper",
            op=op,
            file=file,
            line=line_of(text, match.start()),
            start=match.start(),
            body_start=brace,
            body_end=body_end,
            parent=None,
        )
        node.binders = enclosing_new(binders, match.start())
        while stack and stack[-1][0] < match.start():
            stack.pop()
        if stack:
            node.parent = stack[-1][1].key
            stack[-1][1].nested.append(node.key)
        stack.append((body_end, node))
        nodes.append(node)

    # Scan each node's *self* body: mask the bodies of nested contracts so an
    # arm's access set is not polluted by the arms it creates.
    children: dict[str, list[Node]] = {}
    for node in nodes:
        if node.parent:
            children.setdefault(node.parent, []).append(node)
    for node in nodes:
        chars = list(text[node.body_start:node.body_end + 1])
        for child in children.get(node.key, []):
            lo = child.start - node.body_start
            hi = child.body_end - node.body_start
            for i in range(max(0, lo), min(len(chars), hi + 1)):
                chars[i] = "\n" if chars[i] == "\n" else " "
        body = "".join(chars)
        node.peeks = sorted({n for n in PEEK.findall(body) if n.endswith("State")})
        node.consumes = sorted({n for n in CONSUME.findall(body) if n.endswith("State")})
        all_sends = sorted(set(POST.findall(body)))
        node.sends = all_sends
        node.posts = [name for name in all_sends if name.endswith("State")]
        # State cells created by a `new` inside this body. Posting one is
        # initialisation, not a peek-then-post duplicate.
        node.fresh = sorted({name for _start, _end, bound in collect_new_binders(body)
                             for name in bound if name.endswith("State")})
        node.refusals = sorted(set(REFUSAL.findall(body)))
        node.fail_paths = len(FAIL.findall(body))
        node.send_ops = sorted({f"{a}@{b}" for a, b in SEND_OP.findall(body)})
        # Positioned events let the checker reason about take → refusal → post
        # order on a single path, not just set membership.
        positioned: list[tuple[int, str, str]] = []
        for kind, pattern in (("peek", PEEK), ("take", CONSUME), ("post", POST)):
            for hit in pattern.finditer(body):
                cell = hit.group(1)
                if cell.endswith("State"):
                    positioned.append((hit.start(), kind, cell))
        positioned.sort()
        node.events = [
            {"kind": kind, "cell": cell,
             "line": line_of(text, node.body_start + start),
             "path": blocks.path(node.body_start + start)}
            for start, kind, cell in positioned
        ]
        node.refusal_hits = sorted(
            ({"reason": hit.group(1),
              "line": line_of(text, node.body_start + hit.start()),
              "path": blocks.path(node.body_start + hit.start())}
             for hit in REFUSAL.finditer(body)),
            key=lambda hit: hit["line"],
        )
        node.fail_hits = [
            {"line": line_of(text, node.body_start + hit.start()),
             "path": blocks.path(node.body_start + hit.start())}
            for hit in FAIL.finditer(body)
        ]
        # A nested contract shadows an outer binder only when its name is bound
        # both by the outermost `new` and by a different enclosing `new` block.
        if node.parent:
            outer = binders[0][2] if binders else []
            inner_names: list[str] = []
            for start, end, bound in binders[1:]:
                if start <= node.start <= end:
                    inner_names.extend(bound)
            if node.name in outer and node.name in inner_names:
                node.shadowed = [node.name]
    return nodes


def inventory() -> dict:
    files = sorted(DEPLOY.rglob("*.rho"))
    nodes: list[Node] = []
    for path in files:
        text = strip_comments(path.read_text())
        rel = str(path.relative_to(ROOT))
        nodes.extend(contract_nodes(text, rel))
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for node in nodes:
        if node.key in seen and node.kind == "arm":
            duplicates.append(f"{node.key} at {seen[node.key]} and {node.file}:{node.line}")
        seen.setdefault(node.key, f"{node.file}:{node.line}")
    state_cells = sorted({n for node in nodes for n in node.binders if n.endswith("State")})
    return {
        "schema": "rcash.arm-inventory/v1",
        "source": [str(path.relative_to(ROOT)) for path in files],
        "legacy_excluded": [
            "contracts/src/core", "contracts/src/dex", "contracts/src/listing",
            "contracts/src/lock", "contracts/src/oracle", "contracts/src/stable",
            "contracts/src/transfer",
        ],
        "state_cells": state_cells,
        "duplicates": duplicates,
        "arms": [{**asdict(n), "key": n.key} for n in nodes if n.kind == "arm"],
        "helpers": [{**asdict(n), "key": n.key} for n in nodes if n.kind == "helper"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    data = inventory()
    text = json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"
    if data["duplicates"]:
        for duplicate in data["duplicates"]:
            print(f"duplicate arm: {duplicate}", file=sys.stderr)
        return 1
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text)
        print(f"wrote {OUT} ({len(data['arms'])} arms, {len(data['helpers'])} helpers)")
        return 0
    if args.check:
        if not OUT.is_file() or OUT.read_text() != text:
            print(f"stale {OUT}; run tools/rho_inventory.py --write", file=sys.stderr)
            return 1
        print(f"arm inventory: ok ({len(data['arms'])} arms, {len(data['helpers'])} helpers)")
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
