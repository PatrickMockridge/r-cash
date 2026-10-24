#!/usr/bin/env python3
"""T1: the fork-point arms on a disposable fixed-node devnet.

A0 is the upstream control (two distinct channels). A is two owners sending a transfer on
opposite sides of a partition; both accepted effects must survive the healing merge. B is
the same owner sending on both sides: the state cell is a serialization domain, so exactly
one deploy must be named in the merge block's ``rejectedDeploys`` and its effect must not
half-apply; the rejected send is then retried under a fresh signed deploy.

The devnet must be running:

    DEVNET_PREFIX=rcash DEVNET_NODE_MEMORY=2g \
      tools/devnet.sh up --validators 4 --fresh --no-autopropose --epoch-length 10

Usage: python3 harness/merge/fork_point.py [--skip-install] [--out DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "harness" / "merge"))

import devnet as dn  # noqa: E402
from chainclient import _strings  # noqa: E402

OUT = ROOT / ".devnet" / "merge-evidence"
KEYS = ROOT / ".devnet" / "merge-keys.json"
STATE = ROOT / ".devnet" / "merge-install.json"
OPS = ROOT / ".devnet" / "merge-ops"
MANIFEST = ROOT / ".devnet" / "merge-manifest.json"
FUND = 100_000_000  # 0.1 REV in drops (one faucet drip is 0.3 REV)
AMOUNT = 20_000_000  # 0.02 REV


def record(steps: list, name: str, value) -> None:
    steps.append({"step": name, "value": value})
    print(f"== {name}: {value}", flush=True)


def keygen() -> dict:
    subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "tools" / "keygen.py"),
            "--out", str(KEYS), "--names", "ownerB", "--count", "1",
            "--http", "http://localhost:40403",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    keys = json.loads(KEYS.read_text())
    # The faucet drips 0.3 REV; ten drips give owner B enough for the account and the
    # transfers. The endpoint is idempotent.
    import urllib.error
    import urllib.request

    # One drip is 0.3 REV, enough for a 0.1 REV account and its fees. The endpoint
    # rate-limits rapid repeats, so do not spray it.
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        "http://localhost:41403/api/v1/faucet",
        data=json.dumps({"address": keys["ownerB"]["address"]}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except urllib.error.HTTPError:
        pass
    return keys


def wait_block(container: str, block_hash: str, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return dn.block_info(container, block_hash)
        except Exception:
            time.sleep(1.0)
    raise RuntimeError(f"{container} did not serve block {block_hash}")


def wait_transfer(container: str, uri: str, block_hash: str,
                  expected: str = "open", timeout: float = 60.0) -> str:
    deadline = time.time() + timeout
    last = "not read"
    while time.time() < deadline:
        last = read_info(container, uri, block_hash)
        if last == expected:
            return last
        time.sleep(1.0)
    return last


def wait_result(container: str, deploy_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = dn.node(container).deploy_status(deploy_id)
        if "ProcessedWithSuccess" in status:
            return status["ProcessedWithSuccess"]
        if "ProcessedWithError" in status:
            raise RuntimeError(
                f"deploy {deploy_id} failed: "
                f"{status['ProcessedWithError'].get('deployError')}"
            )
        time.sleep(0.5)
    raise RuntimeError(f"deploy {deploy_id} not processed")


def term_account_setup(root: str, pub: str, amount: int) -> str:
    return (
        "new rl(`rho:registry:lookup`), rCh, fCh, fc, rCh2, facetCh, "
        "ertpCh, iCh, pCh, fundCh, wCh, dCh, "
        "deployerId(`rho:rchain:deployerId`), deployId(`rho:rchain:deployId`) in {"
        f" rl!(`{root}`, *rCh) | for (Root <- rCh) {{"
        ' Root!("resolve", "component:account-factory", 1, *fCh) |'
        " for (@(true, fUri, _) <- fCh) { rl!(fUri, *fc) | for (Factory <- fc) {"
        f' Factory!("getOrCreate", "{pub}".hexToBytes(), *rCh2) |'
        " for (@(true, account, _) <- rCh2) {"
        ' @account!("depositFacet", "REV", *facetCh) |'
        " for (@(true, facet) <- facetCh) {"
        ' rl!(`rho:rchain:ertp`, *ertpCh) | for (@(_, ERTP) <- ertpCh) {'
        ' @ERTP!("getRevIssuer", *iCh) | for (@(revBrand, issuer) <- iCh) {'
        ' @issuer!("makeEmptyPurse", *pCh) | for (@(true, purse) <- pCh) {'
        f' @purse!("revFund", *deployerId, {amount}, *fundCh) | for (@_ <- fundCh) {{'
        f' @purse!("withdraw", (revBrand, {amount}), *wCh) |'
        ' for (@(true, payment) <- wCh) {'
        ' @facet!("deposit", payment, *dCh) | for (@dd <- dCh) { deployId!(dd) }'
        " } } } } } } } } } } }"
    )


def term_send(root: str, pub: str, amount: int, secret_hash: str, expiry: int) -> str:
    return (
        "new rl(`rho:registry:lookup`), rCh, fCh, fc, rCh2, facetCh, sCh, "
        "deployerId(`rho:rchain:deployerId`), deployId(`rho:rchain:deployId`) in {"
        f" rl!(`{root}`, *rCh) | for (Root <- rCh) {{"
        ' Root!("resolve", "component:account-factory", 1, *fCh) |'
        " for (@(true, fUri, _) <- fCh) { rl!(fUri, *fc) | for (Factory <- fc) {"
        f' Factory!("getOrCreate", "{pub}".hexToBytes(), *rCh2) |'
        " for (@(true, account, _) <- rCh2) {"
        ' @account!("depositFacet", "REV", *facetCh) |'
        " for (@(true, facet) <- facetCh) {"
        f' @account!("sendTransfer", *deployerId, "REV", facet, {amount}, '
        f'"{secret_hash}".hexToBytes(), {expiry}, *sCh) |'
        " for (@x <- sCh) { match x {"
        " (true, id, uri) => deployId!([id, uri])"
        " _ => deployId!(x) } }"
        " } } } } } }"
    )


def read_info(container: str, uri: str, block_hash: str | None = None) -> str:
    """Read a transfer with a signed deploy; explore cannot see the registry."""
    return dn.read_transfer_status(container, uri)


def base_control(steps: list, deployer: dict, timeout: float) -> None:
    base = dn.tip(dn.CONTAINERS[0])
    height = base["blockNumber"]
    dn.partition()
    record(steps, "A0.partition", {"group_a": dn.CONTAINERS[:2], "group_b": dn.CONTAINERS[2:]})
    dn.deploy(dn.CONTAINERS[1], r'@"forkA"!("A")', deployer["secret"], height)
    dn.deploy(dn.CONTAINERS[2], r'@"forkB"!("B")', deployer["secret"], height)
    tip_a, tip_b, _, _ = dn.advance_pair(timeout)
    dn.heal()
    merge = dn.find_merge(dn.CONTAINERS[1], height, [tip_a["blockHash"], tip_b["blockHash"]], timeout)
    if merge is None:
        raise SystemExit("A0: no multi-parent merge appeared")
    read = r'for (@x <- @"forkA"; @y <- @"forkB") { @"out"!((x, y)) }'
    post = json.dumps(dn.explore(dn.CONTAINERS[0], read, merge["blockHash"]).get("expr", []))
    base_values = json.dumps(dn.explore(dn.CONTAINERS[0], read, base["blockHash"]).get("expr", []))
    assert '"A"' in post and '"B"' in post, f"A0 lost a writer: {post}"
    assert '"A"' not in base_values and '"B"' not in base_values, f"A0 base: {base_values}"
    record(steps, "A0.merge", {"merge": merge["blockHash"], "post": post})


def install(steps: list) -> dict:
    proposer = dn.Proposer(dn.CONTAINERS[1], interval=1.0)
    proposer.start()
    try:
        proc = subprocess.run(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                str(ROOT / "harness" / "install_testnet.py"),
                "--node", "http://localhost:41403",
                "--keys", str(ROOT / ".devnet" / "keys.json"),
                "--state", str(STATE),
                "--ops", str(OPS),
                "--admin-keys", str(ROOT / ".devnet" / "keys.json"),
                "--manifest", str(MANIFEST),
                "--fresh",
            ],
            capture_output=True,
            text=True,
            timeout=3600,
        )
    finally:
        proposer.stop()
    if proc.returncode != 0:
        raise SystemExit(f"install failed: {proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")
    record(steps, "install", {"returncode": proc.returncode})
    return json.loads(MANIFEST.read_text())


def owner_account(steps: list, manifest: dict, owner: dict, container: str) -> None:
    height = dn.tip(container)["blockNumber"]
    proposer = dn.Proposer(container, interval=0.5)
    proposer.start()
    try:
        deploy_id = dn.deploy(
            container,
            term_account_setup(manifest["root_uri"], owner["public"], FUND),
            owner["secret"],
            height,
        )
        wait_result(container, deploy_id)
    finally:
        proposer.stop()
    record(steps, f"account.{owner.get('name', '?')}", owner["public"][:16])


def send_submit(container: str, manifest: dict, owner: dict, secret_hash: str,
                expiry: int) -> str:
    """Submit a send without waiting: the partitioned side needs a proposal first."""
    height = dn.tip(container)["blockNumber"]
    return dn.deploy(
        container,
        term_send(manifest["root_uri"], owner["public"], AMOUNT, secret_hash, expiry),
        owner["secret"],
        height,
    )


def send_result(container: str, deploy_id: str) -> str:
    payload = dn.wait_result(container, deploy_id)
    values = _strings(payload.get("deployResult"))
    uri = next((v for v in values if v.startswith("rho:id:")), None)
    if not uri:
        raise RuntimeError(f"send returned no transfer URI: {values}")
    return uri


def pinned(steps: list, name: str, deploy_id: str, container: str) -> dict:
    payload = dn.wait_result(container, deploy_id)
    block = payload.get("block") or {}
    return {"deploy_id": deploy_id, "block": block.get("blockHash"),
            "block_number": block.get("blockNumber")}


def arm_a(steps: list, manifest: dict, owner_a: dict, owner_b: dict, timeout: float) -> None:
    expiry = dn.tip(dn.CONTAINERS[0])["blockNumber"] + 200
    hash_a = hashlib.blake2b(secrets.token_bytes(32), digest_size=32).hexdigest()
    hash_b = hashlib.blake2b(secrets.token_bytes(32), digest_size=32).hexdigest()
    base = dn.tip(dn.CONTAINERS[0])
    height = base["blockNumber"]
    dn.partition()
    record(steps, "A.partition", {"base": base["blockHash"], "height": height})
    deploy_a = send_submit(dn.CONTAINERS[1], manifest, owner_a, hash_a, expiry)
    deploy_b = send_submit(dn.CONTAINERS[2], manifest, owner_b, hash_b, expiry)
    tip_a, tip_b, _, _ = dn.advance_pair(timeout)
    uri_a = send_result(dn.CONTAINERS[1], deploy_a)
    uri_b = send_result(dn.CONTAINERS[2], deploy_b)
    dn.heal()
    merge = dn.find_merge(
        dn.CONTAINERS[1], height, [tip_a["blockHash"], tip_b["blockHash"]], timeout
    )
    if merge is None:
        raise SystemExit("A: no multi-parent merge appeared")
    merge_hash = merge["blockHash"]
    dn.wait_finalized(dn.CONTAINERS[1], merge_hash, timeout)
    views = [wait_block(c, merge_hash) for c in dn.CONTAINERS[:2]]
    posts = {v.get("postStateHash") for v in views}
    assert len(posts) == 1, f"A: nodes disagree on the post-state: {posts}"
    pre = views[0].get("preStateHash")
    assert pre not in {tip_a["postStateHash"], tip_b["postStateHash"]}, (
        "A: the merge pre-state equals a parent post-state"
    )
    assert {tip_a["blockHash"], tip_b["blockHash"]} <= set(views[0].get("justifications") or [])
    proposer = dn.Proposer(dn.CONTAINERS[1], interval=0.5)
    proposer.start()
    try:
        status_a = read_info(dn.CONTAINERS[1], uri_a, merge_hash)
        status_b = read_info(dn.CONTAINERS[1], uri_b, merge_hash)
    finally:
        proposer.stop()
    assert status_a == "open" and status_b == "open", (
        f"A: a transfer did not survive the merge: {status_a} / {status_b}"
    )
    record(steps, "A.merge", {
        "merge": merge_hash, "post": posts.pop(), "transfers": [uri_a, uri_b],
        "statuses": [status_a, status_b],
    })
    dn.docker("restart", dn.CONTAINERS[1])
    dn.wait_all([dn.CONTAINERS[1]], timeout, height)
    again = wait_block(dn.CONTAINERS[1], merge_hash)
    assert again.get("postStateHash") == views[0].get("postStateHash"), (
        "A: the restarted validator derives a different merge post-state"
    )
    proposer = dn.Proposer(dn.CONTAINERS[1], interval=0.5)
    proposer.start()
    try:
        re_a = read_info(dn.CONTAINERS[1], uri_a, merge_hash)
        re_b = read_info(dn.CONTAINERS[1], uri_b, merge_hash)
    finally:
        proposer.stop()
    assert re_a == "open" and re_b == "open", f"A: restart reads differ: {re_a}/{re_b}"
    record(steps, "A.restart", {"post": again.get("postStateHash"), "statuses": [re_a, re_b]})


def arm_b(steps: list, manifest: dict, owner: dict, timeout: float) -> None:
    expiry = dn.tip(dn.CONTAINERS[0])["blockNumber"] + 200
    hash_a = hashlib.blake2b(secrets.token_bytes(32), digest_size=32).hexdigest()
    hash_b = hashlib.blake2b(secrets.token_bytes(32), digest_size=32).hexdigest()
    base = dn.tip(dn.CONTAINERS[0])
    height = base["blockNumber"]
    dn.partition()
    deploy_a = send_submit(dn.CONTAINERS[1], manifest, owner, hash_a, expiry)
    deploy_b = send_submit(dn.CONTAINERS[2], manifest, owner, hash_b, expiry)
    tip_a, tip_b, _, _ = dn.advance_pair(timeout)
    uri_a = send_result(dn.CONTAINERS[1], deploy_a)
    uri_b = send_result(dn.CONTAINERS[2], deploy_b)
    dn.heal()
    merge = dn.find_merge(
        dn.CONTAINERS[1], height, [tip_a["blockHash"], tip_b["blockHash"]], timeout
    )
    if merge is None:
        raise SystemExit("B: no multi-parent merge appeared")
    merge_hash = merge["blockHash"]
    merge_info = wait_block(dn.CONTAINERS[0], merge_hash)
    rejected = {str(item).lower() for item in merge_info.get("rejectedDeploys") or []}
    rejected_now = {d for d in (deploy_a.lower(), deploy_b.lower()) if d in rejected}
    assert len(rejected_now) == 1, (
        f"B: expected exactly one rejected send, got {rejected_now} of {rejected}"
    )
    proposer = dn.Proposer(dn.CONTAINERS[1], interval=0.5)
    proposer.start()
    try:
        status_a = read_info(dn.CONTAINERS[1], uri_a, merge_hash)
        status_b = read_info(dn.CONTAINERS[1], uri_b, merge_hash)
    finally:
        proposer.stop()
    live = [s for s in (status_a, status_b) if s == "open"]
    assert len(live) == 1, f"B: expected exactly one live transfer, got {status_a}/{status_b}"
    record(steps, "B.merge", {
        "merge": merge_hash, "rejected": sorted(rejected_now),
        "statuses": [status_a, status_b],
    })
    # Retry the rejected send on the healed chain. A new deploy is a new signature; the
    # rejected operation moved no value, so reusing the secret hash is safe.
    loser_hash = hash_a if deploy_a.lower() in rejected_now else hash_b
    proposer = dn.Proposer(dn.CONTAINERS[1], interval=0.5)
    proposer.start()
    try:
        deploy_retry = send_submit(dn.CONTAINERS[1], manifest, owner, loser_hash, expiry + 100)
        uri_retry = send_result(dn.CONTAINERS[0], deploy_retry)
    finally:
        proposer.stop()
    proposer = dn.Proposer(dn.CONTAINERS[1], interval=0.5)
    proposer.start()
    try:
        retry_status = read_info(dn.CONTAINERS[1], uri_retry)
    finally:
        proposer.stop()
    assert retry_status == "open", f"B: retry did not create an open transfer: {retry_status}"
    record(steps, "B.retry", {"deploy": deploy_retry, "uri": uri_retry, "status": retry_status})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--skip-install", action="store_true")
    ap.add_argument("--skip-control", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT / "fork-point.json")
    args = ap.parse_args(argv)

    missing = [c for c in dn.CONTAINERS if dn.docker("inspect", c, check=False).returncode != 0]
    if missing:
        raise SystemExit(
            "missing containers " + ", ".join(missing) + "\nstart:\n"
            "  DEVNET_PREFIX=rcash DEVNET_NODE_MEMORY=2g tools/devnet.sh up "
            "--validators 4 --fresh --no-autopropose --epoch-length 10"
        )

    keys = json.loads(KEYS.read_text()) if KEYS.is_file() else keygen()
    deployer = keys["deployer"]
    owner_b = keys.get("ownerB") or keys.get("key1")
    if not owner_b:
        raise SystemExit("no second owner key; delete .devnet/merge-keys.json and rerun")
    owner_b["name"] = "ownerB"
    deployer["name"] = "deployer"

    steps: list = []
    dn.wait_all(dn.CONTAINERS, args.timeout)
    if not args.skip_control:
        base_control(steps, deployer, args.timeout)
    if args.skip_install:
        manifest = json.loads(MANIFEST.read_text())
        record(steps, "install", {"skipped": True})
    else:
        manifest = install(steps)

    owner_account(steps, manifest, deployer, dn.CONTAINERS[1])
    owner_account(steps, manifest, owner_b, dn.CONTAINERS[1])

    arm_a(steps, manifest, deployer, owner_b, args.timeout)
    arm_b(steps, manifest, deployer, args.timeout)

    evidence = {"provenance": dn.provenance(), "steps": steps}
    dn.write(args.out, evidence)
    print(f"evidence: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
