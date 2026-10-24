#!/usr/bin/env python3
"""Shared mechanics for the disposable, fixed-node merge arms.

The containers are started by the caller:

    DEVNET_PREFIX=rcash DEVNET_NODE_MEMORY=2g \
      tools/devnet.sh up --validators 4 --fresh --no-autopropose --epoch-length 10

`--no-autopropose` makes the tips controllable. During installation a proposer thread
drives the bootstrap so the installer's inclusion checks can complete; the fork arms stop
it and propose explicitly.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "harness"))

from chainclient import Node  # noqa: E402

PREFIX = os.environ.get("DEVNET_PREFIX", "rcash")
NETWORK = os.environ.get("DEVNET_NETWORK", "devnet")
SHARD = "/root"
DEPLOYER_KEY = "a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76"
CONTAINERS = [
    f"{PREFIX}-bootstrap",
    f"{PREFIX}-validator-1",
    f"{PREFIX}-validator-2",
    f"{PREFIX}-validator-3",
]
FORK_NETWORK = f"{PREFIX}-fork-b"
DEPLOY_RE = re.compile(r"DeployId is: ([0-9a-fA-F]+)")


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=check, text=True, capture_output=True)


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["docker", *args], check=check)


def node(container: str) -> Node:
    return Node("http://127.0.0.1:40403", container=container)


def status(container: str) -> dict:
    return node(container).status()


def wait_all(containers: list[str], timeout: float, minimum_height: int = 1) -> list[int]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            heights = [int(status(c)["latestBlockNumber"]) for c in containers]
            if all(h >= minimum_height for h in heights):
                return heights
        except Exception:
            pass
        time.sleep(1.0)
    raise SystemExit(f"the devnet did not reach height {minimum_height}: {containers}")


def block_info(container: str, block_hash: str) -> dict:
    value = node(container).block(block_hash)
    return value.get("blockInfo", value)


def blocks(container: str, depth: int = 50) -> list[dict]:
    value = node(container).request("GET", f"/api/blocks/{depth}").json()
    if isinstance(value, dict):
        return value.get("blocks", [])
    return value


def tip(container: str) -> dict | None:
    infos = blocks(container, 50)
    return max(infos, key=lambda b: b.get("blockNumber", 0)) if infos else None


def deploy(container: str, term: str, secret: str, height: int,
           phlo_limit: int = 2_000_000) -> str:
    encoded = base64.b64encode(term.encode()).decode()
    path = f"/tmp/rcash-merge-{abs(hash(term)) % 1_000_000}.rho"
    run(["docker", "exec", container, "sh", "-c",
         f"echo {encoded} | base64 -d > {path}"])
    proc = run([
        "docker", "exec", container, "rnode", "deploy",
        "--phlo-limit", str(phlo_limit), "--phlo-price", "1",
        "--private-key", secret, "--shard-id", SHARD,
        "--valid-after-block-number", str(height), path,
    ], check=False)
    out = (proc.stdout or "") + (proc.stderr or "")
    match = DEPLOY_RE.search(out)
    if not match:
        clean = out.split("___ Begin jemalloc statistics ___")[0].strip()
        raise RuntimeError(f"deploy failed in {container}: {clean[:2000]}")
    return match.group(1)


def propose(container: str) -> None:
    run(["docker", "exec", container, "rnode", "propose"], check=False)


class Proposer(threading.Thread):
    """Propose on one node until stopped. Used only while installing."""

    def __init__(self, container: str, interval: float = 1.0):
        super().__init__(daemon=True)
        self.container = container
        self.interval = interval
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            propose(self.container)
            self.stop_event.wait(self.interval)

    def stop(self) -> None:
        self.stop_event.set()
        self.join(timeout=5)


def partition() -> None:
    """Split into bootstrap+validator-1 and validator-2+validator-3.

    The isolated pair is moved to its own bridge so the two can still reach each other;
    disconnecting them from `devnet` alone would leave each without a quorum partner.
    """
    docker("network", "create", FORK_NETWORK, check=False)
    for isolated in (CONTAINERS[2], CONTAINERS[3]):
        docker("network", "disconnect", NETWORK, isolated, check=False)
        docker("network", "connect", FORK_NETWORK, isolated)


def heal() -> None:
    for isolated in (CONTAINERS[2], CONTAINERS[3]):
        docker("network", "disconnect", FORK_NETWORK, isolated, check=False)
        docker("network", "connect", NETWORK, isolated)


def wait_advance(container: str, before: int, timeout: float) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = tip(container)
        if current and current.get("blockNumber", 0) > before:
            return current
        propose(container)
        time.sleep(1.5)
    raise SystemExit(f"{container} did not advance past {before}")


def advance_pair(timeout: float) -> tuple[dict, dict, int, int]:
    """Advance both sides one block past their current tips and return the new tips."""
    before_a = tip(CONTAINERS[1])["blockNumber"]
    before_b = tip(CONTAINERS[2])["blockNumber"]
    tip_a = wait_advance(CONTAINERS[1], before_a, timeout)
    tip_b = wait_advance(CONTAINERS[2], before_b, timeout)
    if tip_a["blockHash"] == tip_b["blockHash"]:
        raise SystemExit("both sides produced the same block: no fork")
    return tip_a, tip_b, before_a, before_b


def find_merge(container: str, height: int, tips: list[str], timeout: float) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        propose(container)
        for info in blocks(container, 25):
            if (
                info.get("blockNumber", 0) > height
                and set(tips) <= set(info.get("justifications") or [])
            ):
                return info
        time.sleep(1.5)
    return None


def explore(container: str, term: str, block_hash: str, pre: bool = False) -> dict:
    return node(container).explore_at(term, block_hash, pre)


def read_strings(container: str, term: str, block_hash: str) -> list[str]:
    from chainclient import _strings

    return _strings(explore(container, term, block_hash))


def provenance() -> dict:
    source = Path("/home/patrick/rholo-fixed")
    sha = run(["git", "-C", str(source), "rev-parse", "HEAD"]).stdout.strip()
    image = run(["docker", "image", "inspect", "rnode:local", "--format", "{{.Id}}"]).stdout.strip()
    label = run([
        "docker", "image", "inspect", "rnode:local",
        "--format", '{{index .Config.Labels "GIT_HEAD_COMMIT"}}',
    ], check=False).stdout.strip()
    return {"source_sha": sha, "image_id": image, "image_label": label,
            "prefix": PREFIX, "network": NETWORK, "containers": CONTAINERS}


def write(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")


def wait_result(container: str, deploy_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = node(container).deploy_status(deploy_id)
        if "ProcessedWithSuccess" in status:
            return status["ProcessedWithSuccess"]
        if "ProcessedWithError" in status:
            raise RuntimeError(
                f"deploy {deploy_id} failed: "
                f"{status['ProcessedWithError'].get('deployError')}"
            )
        time.sleep(0.5)
    raise RuntimeError(f"deploy {deploy_id} not processed")


def read_term(container: str, term: str, secret: str = DEPLOYER_KEY) -> list:
    """Signed read. The fixed node's explore cannot see the native registry."""
    height = tip(container)["blockNumber"]
    deploy_id = deploy(container, term, secret, height)
    payload = wait_result(container, deploy_id)
    return payload.get("deployResult") or []


def read_strings_signed(container: str, term: str, secret: str = DEPLOYER_KEY) -> list[str]:
    from chainclient import _strings

    return _strings(read_term(container, term, secret))


def read_root_keys(container: str, root: str, secret: str = DEPLOYER_KEY) -> list[str]:
    term = (
        f"new rl(`rho:registry:lookup`), rCh, Root, out, "
        f"deployId(`rho:rchain:deployId`) in {{ rl!(`{root}`, *rCh) |"
        ' for (Root <- rCh) { Root!("keys", *out) } |'
        " for (@x <- out) { deployId!(x) } }"
    )
    return read_strings_signed(container, term, secret)


def read_transfer_status(container: str, uri: str, secret: str = DEPLOYER_KEY) -> str:
    term = (
        f"new rl(`rho:registry:lookup`), tCh, TC, out, "
        f"deployId(`rho:rchain:deployId`) in {{ rl!(`{uri}`, *tCh) |"
        ' for (TC <- tCh) { TC!("info", *out) } |'
        " for (@x <- out) { deployId!(x) } }"
    )
    text = " ".join(read_strings_signed(container, term, secret))
    for status in ("open", "claimed", "refunded", "closed"):
        if status in text:
            return status
    return text or "absent"


def wait_finalized(container: str, block_hash: str, timeout: float = 180.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if node(container).is_finalized(block_hash):
                return
        except Exception:
            pass
        propose(container)
        time.sleep(1.0)
    raise RuntimeError(f"{container} did not finalize {block_hash}")
