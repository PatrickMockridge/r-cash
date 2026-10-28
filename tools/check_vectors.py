#!/usr/bin/env python3
"""Compatibility wrapper: vectors are generated and checked by gen_vectors.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from gen_vectors import main  # noqa: E402

raise SystemExit(main(["--check"]))
