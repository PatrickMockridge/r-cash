#!/usr/bin/env python3
"""Advance an idle chain with cheap unique deploys while suites run.

Public testnet has no autopropose: a block appears only when a deploy arrives.
Suites that sleep or wait for height need a block source. The ticker is a
separate process so a suite failure cannot leave it running unnoticed; the
campaign runner starts it before a suite and kills it after.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import deploy as node  # noqa: E402
import netconfig  # noqa: E402


def main() -> int:
    if not netconfig.is_testnet():
        raise SystemExit("ticker is only for an idle public testnet")
    count = 0
    while True:
        try:
            node.tick()
            count += 1
            print(f"tick {count} height={node.height()}", flush=True)
        except KeyboardInterrupt:
            return 0
        except Exception as error:  # keep producing; report the refusal
            print(f"tick failed: {error}", file=sys.stderr, flush=True)
        time.sleep(netconfig.TICKER_INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
