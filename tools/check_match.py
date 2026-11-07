#!/usr/bin/env python3
"""Pattern conformance checks for the deploy sources.

`match` is Rholang's most expressive primitive, and `for` receives use the
same pattern language.  Both are partial: a `match` with no matching arm
reduces to the empty process, and a receive whose pattern does not match never
runs its continuation.  Neither is an error, so a missing arm is a silent
liveness failure (WF2/WF6/L1).

These checks make the cheap, high-signal parts of that obligation mechanical.
They are textual (brace matching plus regex), the same style as
`check_captures.py` and `check_primitives.py`; they do not parse Rholang.

    python3 tools/check_match.py --report
    python3 tools/check_match.py --check          # fail on new findings vs baseline
    python3 tools/check_match.py --strict         # fail on any finding
    python3 tools/check_match.py --write-baseline # record the current findings
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from rho_inventory import matching, strip_comments

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts" / "src" / "deploy" / "v3"
BASELINE = ROOT / "tools" / "match_baseline.json"

KEYWORDS = {"true", "false", "Nil"}
LITERAL_KINDS = {"literal", "int", "string", "tuple-tagged", "tuple-string", "empty-collection"}
BINDING_KINDS = {"wildcard", "variable", "tuple-binding"}
CLOSERS = {"(": ")", "[": "]", "{": "}"}


@dataclass
class Arm:
    pattern: str
    body: str
    kind: str
    line: int


@dataclass
class Match:
    line: int
    offset: int
    body_open: int
    scrutinee: str
    arms: list[Arm] = field(default_factory=list)


@dataclass
class ReceiveClause:
    for_pos: int
    pattern: str
    line: int
    kind: str


@dataclass
class Finding:
    rule: str
    file: str
    line: int
    detail: str
    severity: str = "error"

    @property
    def key(self) -> str:
        return f"{self.file}:{self.line}:{self.rule}:{self.detail}"


# ---------------------------------------------------------------------------
# small scanners


def skip_string(text: str, i: int) -> int:
    """Return the index just past the string starting at i."""
    i += 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return i + 1
        i += 1
    return i


def skip_group(text: str, i: int) -> int:
    return matching(text, i, text[i], CLOSERS[text[i]]) + 1


def split_top(text: str, sep: str) -> list[tuple[str, int]]:
    """Split on `sep` at bracket depth 0, returning (part, offset)."""
    parts: list[tuple[str, int]] = []
    start = 0
    depth = 0
    i = 0
    while i < len(text):
        c = text[i]
        if c == '"':
            i = skip_string(text, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and text.startswith(sep, i):
            parts.append((text[start:i], start))
            i += len(sep)
            start = i
            continue
        i += 1
    parts.append((text[start:], start))
    return parts


def line_at(text: str, offset: int, base: int = 1) -> int:
    return base + text.count("\n", 0, offset)


def pattern_kind(pattern: str) -> str:
    p = pattern.strip()
    if p.startswith("@"):
        p = p[1:].strip()
    if p == "_":
        return "wildcard"
    if p in KEYWORDS:
        return "literal"
    if re.fullmatch(r"\d+", p):
        return "int"
    if re.fullmatch(r'"(?:[^"\\]|\\.)*"', p):
        return "string"
    if re.fullmatch(r"[A-Za-z_]\w*", p):
        return "variable"
    if p[:1] in "([" and p[-1:] in ")]" and len(p) > 1:
        inner = p[1:-1].strip()
        if not inner:
            return "empty-collection"
        sub = [pattern_kind(part) for part, _ in split_top(inner, ",") if part.strip()]
        if sub and all(kind in ("wildcard", "variable") for kind in sub):
            return "tuple-binding"
        if any(kind == "string" for kind in sub):
            return "tuple-string"
        return "tuple-tagged"
    return "other"


def is_binding(kind: str) -> bool:
    return kind in BINDING_KINDS


def collection_parts(pattern: str) -> list[str] | None:
    p = pattern.strip()
    if p.startswith("@"):
        p = p[1:].strip()
    if p[:1] in "([" and p[-1:] in ")]" and len(p) > 1:
        inner = p[1:-1].strip()
        if not inner:
            return []
        return [part for part, _ in split_top(inner, ",") if part.strip()]
    return None


def arm_is_total(arm: Arm, scrutinee: str) -> bool:
    """An arm that cannot fail on any value, or a constructed-tuple destructure."""
    if arm.kind in ("wildcard", "variable"):
        return True
    if arm.kind == "tuple-binding":
        subject = collection_parts(scrutinee)
        pattern = collection_parts(arm.pattern)
        if subject is not None and pattern is not None and len(subject) == len(pattern):
            return True
    return False


# ---------------------------------------------------------------------------
# match parsing


def _body_candidate(body: str) -> bool:
    """True if the brace body looks like match arms (top-level `=>` before `:`)."""
    depth = 0
    i = 0
    while i < len(body):
        c = body[i]
        if c == '"':
            i = skip_string(body, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0:
            if body.startswith("=>", i):
                return True
            if c == ":":
                return False
        i += 1
    return False


def find_body(text: str, start: int) -> tuple[int, int, str] | None:
    """From just after `match`, find the arm body (skipping map literals)."""
    j = start
    while j < len(text):
        c = text[j]
        if c == '"':
            j = skip_string(text, j)
            continue
        if c in "([":
            j = skip_group(text, j)
            continue
        if c == "{":
            end = matching(text, j, "{", "}")
            body = text[j + 1:end]
            if _body_candidate(body):
                return j, end, body
            j = end + 1
            continue
        j += 1
    return None


def split_arms(body: str, base_line: int) -> list[Arm]:
    arms: list[Arm] = []
    i = 0
    start = 0
    while i < len(body):
        c = body[i]
        if c == '"':
            i = skip_string(body, i)
            continue
        if c in "([":
            i = skip_group(body, i)
            continue
        if body.startswith("=>", i):
            pattern = body[start:i].strip()
            j = i + 2
            while j < len(body) and body[j].isspace():
                j += 1
            if j < len(body) and body[j] == "{":
                end = matching(body, j, "{", "}")
                arm_body = body[j:end + 1]
                i = end + 1
            else:
                arm_body = body[j:]
                i = len(body)
            arms.append(
                Arm(pattern=pattern, body=arm_body,
                    kind=pattern_kind(pattern), line=line_at(body, start, base_line))
            )
            start = i
            continue
        i += 1
    return arms


def scan_matches(text: str) -> list[Match]:
    matches: list[Match] = []
    for token in re.finditer(r"\bmatch\b", text):
        found = find_body(text, token.end())
        if not found:
            continue
        brace, _, body = found
        scrutinee = text[token.end():brace].strip()
        matches.append(
            Match(
                line=line_at(text, token.start()),
                offset=token.start(),
                body_open=brace,
                scrutinee=scrutinee,
                arms=split_arms(body, line_at(text, brace + 1)),
            )
        )
    return matches


# ---------------------------------------------------------------------------
# receive parsing


def scan_receives(text: str) -> list[ReceiveClause]:
    clauses: list[ReceiveClause] = []
    for token in re.finditer(r"\bfor\s*\(", text):
        open_paren = text.index("(", token.start())
        close_paren = matching(text, open_paren, "(", ")")
        inside = text[open_paren + 1:close_paren]
        for part, offset in split_top(inside, ";"):
            arrow = split_top(part, "<-")
            if len(arrow) < 2:
                continue
            pattern = arrow[0][0].strip()
            # `<<-` splits as `<-` after a `<`; trim the stray marker.
            pattern = pattern.rstrip("<").strip()
            clauses.append(
                ReceiveClause(
                    for_pos=token.start(),
                    pattern=pattern,
                    line=line_at(inside, offset, line_at(text, token.start())),
                    kind=pattern_kind(pattern),
                )
            )
    return clauses


# ---------------------------------------------------------------------------
# rule helpers


def reply_arguments(body: str) -> list[str]:
    """Return the argument text of every ret!/ret2! send in a body."""
    out: list[str] = []
    for token in re.finditer(r"\bret2?!\s*\(", body):
        open_paren = body.index("(", token.start())
        close_paren = matching(body, open_paren, "(", ")")
        out.append(body[open_paren + 1:close_paren].strip())
    return out


def replies_bare_literal(arg: str) -> bool:
    """A reply that is a bare bool/zero tuple and carries no reason or value."""
    arg = arg.strip()
    # `(true, value)` is a successful payload, not a silent failure fallback.
    if arg.startswith("(true"):
        return False
    if re.search(r"\b1\s*/\s*0\b", arg):
        return False
    if re.search(r'"(?:[^"\\]|\\.)*"', arg):
        return False
    # A forwarded variable or a real value is fine.
    if re.search(r"\b[A-Za-z_]\w*\b", arg):
        names = set(re.findall(r"\b[A-Za-z_]\w*\b", arg))
        if names - KEYWORDS:
            return False
    return bool(re.fullmatch(r"\(?\s*(true|false|0)\s*(,\s*(true|false|0))?\s*\)?", arg))


def enclosing_contract(clean: str, pos: int) -> tuple[str, int] | None:
    name = None
    start = 0
    for token in re.finditer(r"\bcontract\s+([A-Za-z_]\w*)\s*\(", clean):
        if token.start() > pos:
            break
        name = token.group(1)
        start = token.start()
    if name is None:
        return None
    return name, start


def header_binders(clean: str, start: int) -> set[str]:
    """Contract parameters only; for-binders need real scope tracking."""
    names: set[str] = set()
    header = re.search(r"contract\s+[A-Za-z_]\w*\s*\(", clean[start:])
    if header:
        open_paren = start + header.end() - 1
        close_paren = matching(clean, open_paren, "(", ")")
        for part, _ in split_top(clean[open_paren + 1:close_paren], ","):
            bare = re.sub(r'"(?:[^"\\]|\\.)*"', "", part)
            names.update(re.findall(r"[A-Za-z_]\w*", bare))
    return names - KEYWORDS


def _paren_keyword(clean: str, close: int) -> str | None:
    """For the `)` at index close, return the keyword before its `(`."""
    depth = 0
    k = close
    while k >= 0:
        if clean[k] == ")":
            depth += 1
        elif clean[k] == "(":
            depth -= 1
            if depth == 0:
                word = re.search(r"([A-Za-z_]\w*)\s*$", clean[max(0, k - 20):k])
                return word.group(1) if word else None
        k -= 1
    return None


def control_depth(clean: str, pos: int, tree: "BlockTreeLite",
                  match_opens: set[int]) -> int:
    """Approximate for/match/if nesting around a position."""
    depth = 0
    for opener in tree.ancestors(pos):
        if opener in match_opens:
            depth += 1
            continue
        j = opener - 1
        while j >= 0 and clean[j].isspace():
            j -= 1
        if j >= 0 and clean[j] == ")" and _paren_keyword(clean, j) in ("for", "if"):
            depth += 1
    return depth


class BlockTreeLite:
    """Minimal brace tree for depth and enclosing-scope queries."""

    def __init__(self, text: str):
        self.parent: dict[int, int | None] = {}
        self.end: dict[int, int] = {}
        stack: list[int] = []
        for index, char in enumerate(text):
            if char == "{":
                self.parent[index] = stack[-1] if stack else None
                stack.append(index)
            elif char == "}" and stack:
                self.end[stack.pop()] = index

    def ancestors(self, pos: int) -> list[int]:
        return sorted(
            (opener for opener, end in self.end.items() if opener < pos < end),
            reverse=True,
        )


# ---------------------------------------------------------------------------
# checks


def check_file(path: Path) -> tuple[list[Finding], dict]:
    raw = path.read_text()
    text = strip_comments(raw)
    rel = str(path.relative_to(ROOT))
    raw_lines = raw.splitlines()
    findings: list[Finding] = []

    def annotated(line: int) -> bool:
        """A reviewed `// match-total: <reason>` near the match suppresses G-MATCH-01."""
        for number in range(max(0, line - 2), min(len(raw_lines), line + 2)):
            if "match-total:" in raw_lines[number]:
                return True
        return False
    stats: dict = {
        "matches": 0,
        "arms": Counter(),
        "receives": 0,
        "partial_receives": 0,
        "let_matches": 0,
        "depths": Counter(),
    }

    matches = scan_matches(text)
    stats["matches"] = len(matches)
    tokens = len(re.findall(r"\bmatch\b", text))
    if tokens != len(matches):
        findings.append(
            Finding("G-MATCH-00", rel, 1,
                    f"parsed {len(matches)} of {tokens} match tokens")
        )
    tree = BlockTreeLite(text)
    match_opens = {match.body_open for match in matches}

    for match in matches:
        if not match.arms:
            findings.append(Finding("G-MATCH-12", rel, match.line, "no arms"))
            continue
        for arm in match.arms:
            stats["arms"][arm.kind] += 1

        if not annotated(match.line) and not any(
                arm_is_total(arm, match.scrutinee) for arm in match.arms):
            findings.append(
                Finding("G-MATCH-01", rel, match.line,
                        f"partial match: {', '.join(a.pattern for a in match.arms)[:60]}")
            )
        for i, arm in enumerate(match.arms):
            if arm.kind in ("wildcard", "variable") and i != len(match.arms) - 1:
                findings.append(
                    Finding("G-MATCH-02", rel, arm.line,
                            f"unreachable arms after {arm.pattern!r}")
                )
        seen: set[str] = set()
        for arm in match.arms:
            if is_binding(arm.kind):
                continue
            normalized = re.sub(r"\s+", " ", arm.pattern)
            if normalized in seen:
                findings.append(
                    Finding("G-MATCH-02", rel, arm.line,
                            f"duplicate arm {arm.pattern!r}")
                )
            seen.add(normalized)

        scrutinee = match.scrutinee.strip()
        if re.fullmatch(r"[A-Za-z_]\w*", scrutinee):
            for arm in match.arms:
                if arm.kind == "variable" and arm.pattern.strip().lstrip("@") == scrutinee:
                    findings.append(
                        Finding("G-MATCH-03", rel, arm.line,
                                f"pattern {arm.pattern!r} shadows the scrutinee")
                    )
        scope = enclosing_contract(text, match.offset)
        if scope:
            binders = header_binders(text, scope[1])
            for arm in match.arms:
                if arm.kind == "variable" and arm.pattern.strip().lstrip("@") in binders:
                    findings.append(
                        Finding("G-MATCH-03", rel, arm.line,
                                f"pattern {arm.pattern!r} shadows an in-scope binder")
                    )

        if len(match.arms) == 1 and match.arms[0].kind == "variable":
            stats["let_matches"] += 1
            chain = 1
            current = scan_matches(match.arms[0].body)
            while len(current) == 1 and len(current[0].arms) == 1 \
                    and current[0].arms[0].kind == "variable":
                chain += 1
                current = scan_matches(current[0].arms[0].body)
            if chain >= 2:
                findings.append(
                    Finding("G-MATCH-08", rel, match.line,
                            f"let-chain depth {chain}", severity="warning")
                )

        depth = 1 + control_depth(text, match.offset, tree, match_opens)
        stats["depths"][depth] += 1

        if re.search(r"\bargs\.nth\s*\(", match.scrutinee):
            start = scope[1] if scope else 0
            before = text[max(start, match.offset - 2000):match.offset]
            if "args.length()" not in before:
                findings.append(
                    Finding("G-MATCH-10", rel, match.line,
                            "args.nth without an args.length guard")
                )

        for arm in match.arms:
            if arm.kind != "wildcard":
                continue
            replies = reply_arguments(arm.body)
            if replies and all(replies_bare_literal(reply) for reply in replies):
                findings.append(
                    Finding("G-MATCH-06", rel, arm.line,
                            f"catch-all replies without a reason: {replies[0][:40]}")
                )

    for token in re.finditer(r"\.set\s*\(\s*[^,()]+,\s*Nil\s*\)", text):
        findings.append(
            Finding("G-MATCH-04", rel, line_at(text, token.start()),
                    "Nil stored as a map value")
        )

    receives = scan_receives(text)
    stats["receives"] = len(receives)
    partial_fors: set[int] = set()
    for clause in receives:
        if clause.kind in LITERAL_KINDS:
            stats["partial_receives"] += 1
            partial_fors.add(clause.for_pos)
            findings.append(
                Finding("G-MATCH-05", rel, clause.line,
                        f"success-only receive {clause.pattern!r}")
            )
    stats["partial_receive_fors"] = len(partial_fors)

    for token in re.finditer(r"\bif\s*\(", text):
        open_paren = text.index("(", token.start())
        close_paren = matching(text, open_paren, "(", ")")
        condition = text[open_paren + 1:close_paren]
        if "||" in condition or "&&" in condition:
            continue
        if not re.search(r'(==|!=)\s*"', condition):
            continue
        left = re.split(r"(==|!=)", condition)[0].strip()
        if ".get(" not in left and not re.fullmatch(r"[A-Za-z_]\w*", left):
            continue
        findings.append(
            Finding("G-MATCH-07", rel, line_at(text, token.start()),
                    f"tag dispatch via if: {left}", severity="warning")
        )

    for header in re.finditer(r"\bcontract\s+([A-Za-z_]\w*)\s*\(", text):
        open_paren = text.index("(", header.start())
        close_paren = matching(text, open_paren, "(", ")")
        body_open = text.find("{", close_paren)
        if body_open < 0:
            continue
        body_close = matching(text, body_open, "{", "}")
        body = text[body_open:body_close]
        if re.search(r"\bret2?!\s*\(\s*(true|false)\s*\)", body):
            findings.append(
                Finding("G-MATCH-11", rel, line_at(text, header.start()),
                        f"helper {header.group(1)} replies with a bare bool",
                        severity="warning")
            )

    deep = sum(count for depth, count in stats["depths"].items() if depth > 4)
    if deep:
        findings.append(
            Finding("G-MATCH-09", rel, 1,
                    f"{deep} matches deeper than 4 (max {max(stats['depths'])})",
                    severity="warning")
        )

    return findings, stats


def scan() -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    stats: dict = {
        "files": 0,
        "matches": 0,
        "arms": Counter(),
        "receives": 0,
        "partial_receives": 0,
        "partial_receive_fors": 0,
        "let_matches": 0,
        "depths": Counter(),
        "per_file": {},
    }
    for path in sorted(CONTRACTS.glob("*.rho")):
        file_findings, file_stats = check_file(path)
        findings.extend(file_findings)
        stats["files"] += 1
        stats["matches"] += file_stats["matches"]
        stats["arms"].update(file_stats["arms"])
        stats["receives"] += file_stats["receives"]
        stats["partial_receives"] += file_stats["partial_receives"]
        stats["partial_receive_fors"] += file_stats["partial_receive_fors"]
        stats["let_matches"] += file_stats["let_matches"]
        stats["depths"].update(file_stats["depths"])
        stats["per_file"][path.name] = {
            "matches": file_stats["matches"],
            "partial_receives": file_stats["partial_receives"],
            "findings": len(file_findings),
        }
    return findings, stats


def print_report(findings: list[Finding], stats: dict) -> None:
    print(f"match review: {stats['matches']} match statements in {stats['files']} files")
    print("  arms: " + " ".join(f"{k}={v}" for k, v in sorted(stats["arms"].items())))
    print(f"  receives: {stats['partial_receives']}/{stats['receives']} clauses "
          f"success-only in {stats['partial_receive_fors']} receive statements")
    print(f"  let-matches: {stats['let_matches']}")
    print("  depth: " + " ".join(f"{k}={v}" for k, v in sorted(stats["depths"].items())))
    rules = Counter(f.rule for f in findings)
    print("  findings: " + " ".join(f"{k}={v}" for k, v in sorted(rules.items())) or "  findings: none")
    by_file = defaultdict(list)
    for finding in findings:
        by_file[finding.file].append(finding)
    for file in sorted(by_file):
        print(f"\n{file}")
        for finding in sorted(by_file[file], key=lambda f: (f.line, f.rule)):
            print(f"  {finding.line:>5}  {finding.rule}  {finding.detail}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print metrics and all findings")
    ap.add_argument("--check", action="store_true", help="fail on findings not in the baseline")
    ap.add_argument("--strict", action="store_true", help="fail on any finding")
    ap.add_argument("--write-baseline", action="store_true", help="record current findings")
    args = ap.parse_args(argv)

    findings, stats = scan()
    baseline: set[str] = set()
    if BASELINE.is_file():
        baseline = set(json.loads(BASELINE.read_text(encoding="utf-8")).get("keys", []))

    if args.write_baseline:
        BASELINE.write_text(
            json.dumps({"keys": sorted(f.key for f in findings)}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {len(findings)} baseline findings to {BASELINE.relative_to(ROOT)}")
        return 0

    if args.report:
        print_report(findings, stats)
    elif not (args.check or args.strict):
        print(f"matches: {stats['matches']} statements, "
              f"{stats['partial_receives']}/{stats['receives']} success-only receives, "
              f"{len(findings)} finding(s)")

    problems = findings if args.strict else [
        finding for finding in findings if finding.key not in baseline
    ]
    if args.check or args.strict:
        if problems:
            print("match findings not in the baseline:", file=sys.stderr)
            for finding in problems:
                print(f"  {finding.key}", file=sys.stderr)
            return 1
        print(f"match: ok ({len(findings)} findings, {len(baseline)} baselined)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
