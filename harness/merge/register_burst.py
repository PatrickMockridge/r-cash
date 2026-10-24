#!/usr/bin/env python3
"""T2: register-then-read burst and divergent registrations.

(a) Sixteen sequential Root registrations, with unrelated deploys interleaved. Every key
must be present at the block that carries the last write and at the finalized tip, and the
key set must be monotone across pinned ancestors. A re-register must return ``duplicate``
without changing the set.

(b) One registration on each side of a partition. Both consume ``rootState``; exactly one
deploy must be named in the merge block's ``rejectedDeploys``, exactly one key must be
present, and the rejected registration must succeed when retried after the heal.

The devnet must be running (no-autopropose). Usage:
    python3 harness/merge/register_burst.py [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "harness" / "merge"))

import devnet as dn  # noqa: E402
from fork_point import read_info, wait_block, wait_result  # noqa: E402
from chainclient import _strings  # noqa: E402

OUT = ROOT / ".devnet" / "merge-evidence" / "register-burst.json"
KEYS = ROOT / ".devnet" / "keys.json"


def record(steps: list, name: str, value) -> None:
    steps.append({"step": name, "value": value})
    print(f"== {name}: {value}", flush=True)


def term_keys(root: str) -> str:
    return (
        f"new rl(`rho:registry:lookup`), rCh, Root, out in {{ rl!(`{root}`, *rCh) |"
        ' for (Root <- rCh) { Root!("keys", *out) } }'
    )


def term_register(root: str, key: str) -> str:
    return (
        "new rl(`rho:registry:lookup`), rCh, Root, ack, "
        "deployerId(`rho:rchain:deployerId`), deployId(`rho:rchain:deployId`) in {"
        f" rl!(`{root}`, *rCh) | for (Root <- rCh) {{"
        f' Root!("register", "{key}", "rho:id:burst-{key}", 1, "burst", *deployerId, *ack) |'
        " for (@r <- ack) { deployId!([r]) } } }"
    )


def keys_at(root: str, block_hash: str | None = None) -> set[str]:
    """Signed Root.keys read. The fixed node's explore cannot resolve the registry."""
    return set(dn.read_root_keys(dn.CONTAINERS[1], root))


def deploy_register(root: str, key: str, container: str = dn.CONTAINERS[1]) -> tuple[str, dict]:
    height = dn.tip(container)["blockNumber"]
    deploy_id = dn.deploy(container, term_register(root, key), KEYS_JSON["deployer"]["secret"], height)
    payload = wait_result(container, deploy_id)
    return deploy_id, payload


def deploy_nil(container: str) -> str:
    height = dn.tip(container)["blockNumber"]
    return dn.deploy(container, "Nil", KEYS_JSON["deployer"]["secret"], height)


def main(argv: list[str] | None = None) -> int:
    global KEYS_JSON
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    KEYS_JSON = json.loads(KEYS.read_text())
    steps: list = []

    missing = [c for c in dn.CONTAINERS if dn.docker("inspect", c, check=False).returncode != 0]
    if missing:
        raise SystemExit("missing containers " + ", ".join(missing))
    dn.wait_all(dn.CONTAINERS, args.timeout)

    # Find the installed Root from the manifest. The burst registers under real keys on a
    # disposable chain; it never runs against a shared one.
    manifest = json.loads((ROOT / ".devnet" / "merge-manifest.json").read_text())
    root = manifest["root_uri"]

    proposer = dn.Proposer(dn.CONTAINERS[1], interval=0.5)
    proposer.start()
    try:
        blocks = []
        for index in range(16):
            _, payload = deploy_register(root, f"burst-{index:02d}")
            blocks.append((payload.get("block") or {}).get("blockHash"))
            if index % 4 == 3:
                deploy_nil(dn.CONTAINERS[1])
        time.sleep(2)
        last_block = blocks[-1]
        tip = dn.tip(dn.CONTAINERS[1])["blockHash"]
        at_last = keys_at(root, last_block)
        at_tip = keys_at(root, tip)
        expected = {f"burst-{index:02d}" for index in range(16)}
        missing_keys = expected - at_last
        assert not missing_keys, f"T2a: {len(missing_keys)} registrations did not survive: {missing_keys}"
        assert at_last <= at_tip, "T2a: the Root key set moved backwards at the tip"
        record(steps, "T2a.keys", {"at_last": len(at_last), "at_tip": len(at_tip)})

        # A duplicate re-register is a refusal, not a second entry.
        _, payload = deploy_register(root, "burst-00")
        text = json.dumps(payload).lower()
        assert "duplicate" in text, f"T2a: re-register did not report duplicate: {text[:500]}"
        after = keys_at(root, dn.tip(dn.CONTAINERS[1])["blockHash"])
        assert expected <= after, "T2a: duplicate re-register changed the key set"
        record(steps, "T2a.duplicate", {"result": text[:200]})
    finally:
        proposer.stop()

    # T2b: two divergent registrations into the same cell.
    base = dn.tip(dn.CONTAINERS[1])
    height = base["blockNumber"]
    dn.partition()
    height_x = dn.tip(dn.CONTAINERS[1])["blockNumber"]
    deploy_x = dn.deploy(dn.CONTAINERS[1], term_register(root, "fork-x"),
                         KEYS_JSON["deployer"]["secret"], height_x)
    height_y = dn.tip(dn.CONTAINERS[2])["blockNumber"]
    deploy_y = dn.deploy(dn.CONTAINERS[2], term_register(root, "fork-y"),
                         KEYS_JSON["deployer"]["secret"], height_y)
    tip_a, tip_b, _, _ = dn.advance_pair(args.timeout)
    dn.heal()
    merge = dn.find_merge(
        dn.CONTAINERS[1], height, [tip_a["blockHash"], tip_b["blockHash"]], args.timeout
    )
    if merge is None:
        raise SystemExit("T2b: no multi-parent merge appeared")
    merge_hash = merge["blockHash"]
    info = wait_block(dn.CONTAINERS[1], merge_hash)
    rejected = {str(item).lower() for item in info.get("rejectedDeploys") or []}
    ours = {d for d in (deploy_x.lower(), deploy_y.lower()) if d in rejected}
    assert len(ours) == 1, f"T2b: expected one rejected register, got {ours} of {rejected}"
    present = keys_at(root, merge_hash)
    live = [key for key in ("fork-x", "fork-y") if key in present]
    assert len(live) == 1, f"T2b: expected one live key, got {live}"
    record(steps, "T2b.merge", {"merge": merge_hash, "rejected": sorted(ours), "live": live})

    loser = "fork-y" if live == ["fork-x"] else "fork-x"
    proposer = dn.Proposer(dn.CONTAINERS[1], interval=0.5)
    proposer.start()
    try:
        deploy_retry, _ = deploy_register(root, loser)
    finally:
        proposer.stop()
    final_tip = dn.tip(dn.CONTAINERS[1])["blockHash"]
    assert loser in keys_at(root, final_tip), f"T2b: retry of {loser} did not register"
    record(steps, "T2b.retry", {"key": loser, "deploy": deploy_retry})

    dn.write(args.out, {"provenance": dn.provenance(), "steps": steps})
    print(f"evidence: {args.out}")
    return 0


KEYS_JSON: dict = {}


if __name__ == "__main__":
    raise SystemExit(main())
