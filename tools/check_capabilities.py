#!/usr/bin/env python3
"""Check the deploy sources against the object-capability authority model.

The model (docs/spec/00-CALCULUS.md) says authority is an unforgeable `new`-bound
name held in a closure. A caller-supplied name is a sink facet, a payment or a
reply channel, never authority; a published bundle must not capture a
registry-resolved capability; and a privileged arm must compare its authority
argument against a name it already holds.

These are lexical checks in the style of `check_captures.py` and `check_match.py`.
They complement the empirical gates (a fresh install plus the red-team suite in
`harness/unit_ocap.py`); they are not a type system.

Rules:
  G-CAP-AUTH     a privileged arm takes its authority as a caller-supplied value
                 (`@auth`) instead of an unforgeable name, or takes a name-bound
                 authority it never compares.
  G-CAP-STORE    a raw authority name (auth/proof/facet/mint/burn/lock purse) is
                 written into a state map.
  G-CAP-LEAK     an authority name is returned in a reply, attestation or view.
  G-CAP-DOMAIN   a signed preimage is assembled with `toString()`/`"|"` rather
                 than the canonical Codec.
  G-CAP-REGISTRY a published bundle captures a name bound from a registry.
  G-CAP-BUNDLE   design metric: the authority-looking free names in each
                 published bundle (ratcheted, see the baseline).

Usage:
    python3 tools/check_capabilities.py            # report
    python3 tools/check_capabilities.py --check    # fail on new findings vs baseline
    python3 tools/check_capabilities.py --strict   # fail on any finding
    python3 tools/check_capabilities.py --write-baseline
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "contracts" / "src" / "deploy" / "v3"
BASELINE = ROOT / "tools" / "capability_baseline.json"

CONTRACT = re.compile(
    r"contract\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*)\)\s*=\s*\{", re.S
)
NEW = re.compile(r"\bnew\s+([A-Za-z_][A-Za-z0-9_,\s]*?)\s+in\b")
RECEIVE = re.compile(r"for\s*\(([^)]*)\)\s*(?:<-|<<-)\s*([A-Za-z_][A-Za-z0-9_]*)")
BUNDLE = re.compile(r"bundle\+?\{\s*\*([A-Za-z_][A-Za-z0-9_]*)\s*\}")
PUBLISH = re.compile(r"rs!\s*\(\s*bundle\+?\{\s*\*([A-Za-z_][A-Za-z0-9_]*)\s*\}")
REGISTRY_CALL = re.compile(
    r"(Components!|Directory!|ListingRegistry!|Root!|StablecoinDirectory!|"
    r"OracleRegistry!|MarketDirectory!|CurrencyRegistry!|rl!)"
    r"\s*\((.*?)\)",
    re.S,
)
AUTHORITY = re.compile(r"(?i)(auth|proof|lockpurse)")
SIGNED_PREIMAGE = re.compile(r"(?i)(authorize|sign|preimage|payload|argsHash)")

# Sink facets and per-instance capabilities that are documented as returnable.
ALLOW_RETURN = {
    ("PurseStore", "facet"),
    ("VaultBook", "open"),
}


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    detail: str
    channel: str = ""

    @property
    def key(self) -> str:
        return f"{self.file}:{self.line}:{self.rule}:{self.detail}"


def strip_comments(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        in_string = False
        escaped = False
        kept: list[str] = []
        i = 0
        while i < len(line):
            c = line[i]
            if in_string:
                kept.append(c)
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
                kept.append(c)
                i += 1
                continue
            if c == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            kept.append(c)
            i += 1
        out.append("".join(kept))
    return "\n".join(out)


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def matching_brace(text: str, start: int) -> int:
    index = text.find("{", start)
    if index < 0:
        return -1
    depth = 0
    in_string = False
    escaped = False
    i = index
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
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def split_params(raw: str) -> list[str]:
    params: list[str] = []
    depth = 0
    current: list[str] = []
    for c in raw:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            params.append("".join(current).strip())
            current = []
        else:
            current.append(c)
    if current:
        params.append("".join(current).strip())
    return [p for p in params if p]


def top_level_args(raw: str) -> list[str]:
    return split_params(raw)


def fresh_names(text: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"\bnew\b(.*?)\bin\b", text, re.S):
        block = match.group(1)
        for name in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|,|$)", block):
            names.add(name)
    return names


def is_authority(name: str) -> bool:
    return bool(AUTHORITY.search(name))


def findings_for(path: Path) -> list[Finding]:
    rel = str(path.relative_to(ROOT))
    text = strip_comments(path.read_text(encoding="utf-8"))
    fresh = fresh_names(text)
    registry: set[str] = set()
    for match in REGISTRY_CALL.finditer(text):
        call, args = match.group(1), match.group(2)
        if call == "rl!" and args.lstrip().startswith(("`rho:", '"rho:')):
            continue
        for name in re.findall(r"\*([A-Za-z_][A-Za-z0-9_]*)", args):
            registry.add(name)
    findings: list[Finding] = []
    seen: set[str] = set()

    def add(line: int, rule: str, detail: str, channel: str = "") -> None:
        finding = Finding(rel, line, rule, detail, channel)
        if finding.key not in seen:
            seen.add(finding.key)
            findings.append(finding)

    # -- arms -------------------------------------------------------------
    for match in CONTRACT.finditer(text):
        component, raw_params = match.group(1), match.group(2)
        body_end = matching_brace(text, match.end() - 1)
        if body_end < 0:
            continue
        body = text[match.end():body_end]
        line = line_of(text, match.start())
        params = split_params(raw_params)
        op = ""
        if params and params[0].startswith('@"'):
            op = params[0][2:].rstrip('"')
        for param in params[1:]:
            bare = param.lstrip("@")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", bare):
                continue
            if is_authority(bare):
                compared = bool(re.search(
                    rf"(==|!=)\s*\*?{re.escape(bare)}\b|\*?{re.escape(bare)}\s*(==|!=)", body))
                forwarded = bool(re.search(
                    rf"!\s*\([^)]*\b{re.escape(bare)}\b|\*\s*{re.escape(bare)}\b", body))
                if not compared and not forwarded:
                    add(line, "G-CAP-AUTH",
                        f'{component}@"{op}" takes authority {bare} but never checks or forwards it')

        # G-CAP-LEAK: authority returned as a bare reply/view argument.
        for ret in re.finditer(r"\b(ret[0-9]?|deployId)!\s*\((.*?)\)", body, re.S):
            for arg in top_level_args(ret.group(2)):
                sent = re.fullmatch(r"\*\s*([A-Za-z_][A-Za-z0-9_]*)", arg.strip())
                if sent and is_authority(sent.group(1)) and (component, op) not in ALLOW_RETURN:
                    add(line_of(text, match.start() + ret.start()),
                        "G-CAP-LEAK", f'{component}@"{op}" replies with authority {sent.group(1)}')

        # G-CAP-STORE: authority name written into a state map literal.
        for store in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]*)":\s*\*([A-Za-z_][A-Za-z0-9_]*)', body):
            key, name = store.group(1), store.group(2)
            if is_authority(name) or is_authority(key):
                if (component, op) not in {("VaultBook", "open")}:
                    add(line_of(text, match.start() + store.start()),
                        "G-CAP-STORE", f'{component}@{op} stores authority {name} under {key!r}')

        # G-CAP-DOMAIN: non-canonical signed preimage.
        for sep in re.finditer(r'"[^"\n]*\|[^"\n]*"', body):
            start = max(0, sep.start() - 300)
            window = body[start:sep.start() + 300]
            if ".toString()" in window and SIGNED_PREIMAGE.search(window):
                add(line_of(text, match.start() + sep.start()),
                    "G-CAP-DOMAIN",
                    f'{component}@"{op}" builds a signed preimage with toString()/|')

    # -- published bundles ------------------------------------------------
    for publish in PUBLISH.finditer(text):
        name = publish.group(1)
        line = line_of(text, publish.start())
        body = ""
        for match in CONTRACT.finditer(text):
            if match.group(1) == name:
                end = matching_brace(text, match.end() - 1)
                if end >= 0:
                    body = text[match.end():end]
                break
        captured = sorted(
            n for n in re.findall(r"\*([A-Za-z_][A-Za-z0-9_]*)", body)
            if is_authority(n)
        )
        add(line, "G-CAP-BUNDLE",
            f"bundle {name} closes over {', '.join(captured) or 'nothing'}")
        if body and re.search(
            rf"for\s*\([^)]*\b{re.escape(name)}\b[^)]*\)\s*(?:<-|<<-)\s*([A-Za-z_][A-Za-z0-9_]*)",
            text,
        ):
            channel = re.search(
                rf"for\s*\([^)]*\b{re.escape(name)}\b[^)]*\)\s*(?:<-|<<-)\s*([A-Za-z_][A-Za-z0-9_]*)",
                text,
            ).group(1)
            if channel in registry:
                add(line, "G-CAP-REGISTRY",
                    f"bundle {name} is bound from registry channel {channel}", channel)

    findings.sort(key=lambda f: (f.file, f.line, f.rule, f.detail))
    return findings


def scan() -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(SRC.rglob("*.rho")):
        findings.extend(findings_for(path))
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail on new findings vs baseline")
    ap.add_argument("--strict", action="store_true", help="fail on any finding")
    ap.add_argument("--write-baseline", action="store_true", help="record current findings")
    args = ap.parse_args(argv)

    findings = scan()
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

    if args.strict:
        problems = findings
    elif args.check:
        problems = [f for f in findings if f.key not in baseline]
    else:
        problems = []

    for finding in findings:
        label = "known" if finding.key in baseline else "new"
        print(f"{label}: {finding.file}:{finding.line} {finding.rule} {finding.detail}")

    if problems:
        print("capability findings not in the baseline:", file=sys.stderr)
        for finding in problems:
            print(f"  {finding.key}", file=sys.stderr)
        return 1
    print(f"capabilities: ok ({len(findings)} findings, {len(baseline)} baselined)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
