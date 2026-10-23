#!/usr/bin/env python3
"""Fail if R-Cash contains C/C++ sources, dependencies, build tools or artifacts.

This is the enforcement behind docs/LANGUAGES.md. It is deliberately stricter than
"no .cpp files": the project previously pulled C/C++ in through cargo features and
invoked protoc/wasm-opt from scripts. Run with:

    make check-no-cpp
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".ino",
    ".m",
    ".mm",
    ".asm",
}
SOURCE_NAMES = {"CMakeLists.txt"}
ARTIFACT_SUFFIXES = {".o", ".a", ".so", ".dll", ".dylib", ".node"}

# Crates that compile C/C++, invoke a C/C++ tool, or were removed for doing so.
FORBIDDEN_CRATES = {
    "ring",
    "cc",
    "cmake",
    "bindgen",
    "minicov",
    "wasm-bindgen-test",
    "aws-lc-rs",
    "aws-lc-sys",
    "openssl-sys",
    "rchain-models",
    "libz-sys",
    "zstd-sys",
    "lmdb-rkv-sys",
    "secp256k1-sys",
    "tikv-jemalloc-sys",
    "librocksdb-sys",
}
# Rust bindings to JS/OS APIs, not native builds.
NATIVE_SYS_ALLOW = {"js-sys", "web-sys", "windows-sys"}

TOOL_PATTERN = re.compile(
    r"(?<![\w.-])(protoc|wasm-opt|cmake|bindgen|g\+\+|clang\+\+|gcc)(?![\w-])"
)
TOOL_FILES = [
    "Makefile",
    "web/package.json",
    "package.json",
    "web/scripts/build-wasm.mjs",
    "web/tests/wasm-smoke.mjs",
    "web/scripts/wasm-smoke.mjs",
    "tools/build_contracts.py",
    "tools/market_terms.py",
]
TOOL_GLOBS = [
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "harness/**/*.py",
    "tools/*.py",
    "tools/*.sh",
    "crates/**/build.rs",
    "scripts/*.sh",
    "*.sh",
    "Dockerfile*",
    "docker-compose*.yml",
    "docker-compose*.yaml",
]


def fail(title: str, details: list[str]) -> None:
    print(f"error: {title}", file=sys.stderr)
    for detail in details:
        print(f"  {detail}", file=sys.stderr)
    print("See docs/LANGUAGES.md.", file=sys.stderr)
    sys.exit(1)


def git_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        fail("git ls-files failed", [result.stderr.decode(errors="replace")])
    return [
        ROOT / entry
        for entry in result.stdout.decode(errors="replace").split("\0")
        if entry
    ]


def check_sources(files: list[Path]) -> None:
    hits = []
    for path in files:
        suffix = path.suffix
        is_source = (
            suffix in SOURCE_SUFFIXES
            or suffix == ".S"
            or path.name in SOURCE_NAMES
            or suffix == ".cmake"
        )
        if is_source:
            hits.append(str(path.relative_to(ROOT)))
    # The workflow is untracked locally; scan it too.
    for path in sorted((ROOT / ".github/workflows").glob("*")):
        if path.suffix in SOURCE_SUFFIXES or path.suffix == ".S":
            hits.append(str(path.relative_to(ROOT)))
    if hits:
        fail("C/C++ or CMake source files are not allowed", hits)


def check_artifacts(files: list[Path]) -> None:
    hits = [
        str(path.relative_to(ROOT))
        for path in files
        if path.suffix.lower() in ARTIFACT_SUFFIXES
    ]
    if hits:
        fail("native object/shared-library artifacts are not allowed", hits)


def tree_packages(args: list[str]) -> tuple[list[str], str]:
    result = subprocess.run(
        [
            "cargo",
            "tree",
            "--locked",
            "--prefix",
            "none",
            "--format",
            "{p}",
            *args,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return [], result.stderr.strip()
    names = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        names.append(line.split()[0])
    return names, ""


def check_graphs() -> None:
    invocations = [
        ("host", ["--workspace", "--edges", "normal,build"]),
        ("host/all-features", ["--workspace", "--all-features", "--edges", "normal,build"]),
        (
            "wasm32",
            [
                "-p",
                "rcash-wasm",
                "--target",
                "wasm32-unknown-unknown",
                "--edges",
                "normal,build",
            ],
        ),
    ]
    problems = []
    for label, args in invocations:
        names, error = tree_packages(args)
        if error:
            problems.append(f"{label}: cargo tree failed: {error}")
            continue
        forbidden = {
            name
            for name in names
            if name in FORBIDDEN_CRATES
            or (name.endswith("-sys") and name not in NATIVE_SYS_ALLOW)
        }
        if forbidden:
            problems.append(f"{label}: {', '.join(sorted(forbidden))}")
    if problems:
        fail("C/C++-compiling crates are in the dependency graph", problems)


def check_lockfile() -> None:
    lock = ROOT / "Cargo.lock"
    if not lock.exists():
        fail("Cargo.lock is missing", ["run cargo generate-lockfile"])
    text = lock.read_text(encoding="utf-8")
    names = set(re.findall(r'^name = "([^"]+)"$', text, flags=re.MULTILINE))
    forbidden = {
        name
        for name in names
        if name in FORBIDDEN_CRATES
        or (name.endswith("-sys") and name not in NATIVE_SYS_ALLOW)
    }
    if forbidden:
        fail(
            "C/C++-compiling crates are in Cargo.lock (stale lock entries count)",
            sorted(forbidden),
        )


def check_tools() -> None:
    paths: set[Path] = set()
    for rel in TOOL_FILES:
        path = ROOT / rel
        if path.is_file():
            paths.add(path)
    for pattern in TOOL_GLOBS:
        paths.update(ROOT.glob(pattern))
    hits = []
    for path in sorted(paths):
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            match = TOOL_PATTERN.search(line)
            if match:
                hits.append(f"{path.relative_to(ROOT)}:{number}: {match.group(1)}")
    if hits:
        fail("a C/C++ build tool is referenced by an executable/build file", hits)


def main() -> None:
    files = git_files()
    check_sources(files)
    check_artifacts(files)
    check_lockfile()
    check_graphs()
    check_tools()
    print(
        "no-cpp: clean "
        f"({len(files)} tracked files; host and wasm graphs; lockfile; tool scripts)"
    )


if __name__ == "__main__":
    main()
