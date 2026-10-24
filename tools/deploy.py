#!/usr/bin/env python3
"""Deploy and read Rholang on the local rchain-rust devnet.

Deploys go through the node's own CLI inside the devnet container, so no deploy bytes are
reimplemented here.  Reads use the public HTTP API.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import requests

CONTAINER = "devnet-bootstrap"
HTTP = "http://localhost:40403"
ADMIN = "http://localhost:40405"
SHARD = "/root"
DEPLOY_RE = re.compile(r"DeployId is: ([0-9a-fA-F]+)")


class DevnetError(RuntimeError):
    pass


class Refusal(DevnetError):
    """A designed refusal: 429, 503, RESOURCE_EXHAUSTED, duplicate or pool-full."""

    def __init__(self, code: str, detail: str, retry_after: int | None = None):
        super().__init__(f"REFUSED code={code} retry_after={retry_after or 0} detail={detail}")
        self.code = code
        self.retry_after = retry_after


def _json(method: str, path: str, body=None, base: str = HTTP, timeout: int = 30,
          attempts: int = 6):
    url = f"{base}{path}"
    last = "no attempt"
    for attempt in range(attempts):
        retry_after = None
        try:
            if method == "GET":
                resp = requests.get(url, timeout=timeout)
            else:
                resp = requests.post(url, json=body, timeout=timeout)
        except requests.RequestException as error:
            last = str(error)
        else:
            if resp.status_code < 400:
                return None if not resp.text.strip() else resp.json()
            if resp.status_code in (408, 425, 429, 503):
                retry_after = _retry_after(resp)
                last = f"{resp.status_code}: {resp.text[:300]}"
            else:
                raise DevnetError(f"{method} {url} -> {resp.status_code}: {resp.text[:500]}")
        time.sleep(min(0.25 * (2**attempt), 8.0) / 2 + 0.125)
        if retry_after:
            time.sleep(retry_after)
    code = "503" if "503" in last else ("429" if "429" in last else "transport")
    raise Refusal(code, last)


def _retry_after(response) -> int | None:
    raw = response.headers.get("retry-after")
    try:
        return int(str(raw).strip()) if raw is not None else None
    except ValueError:
        return None


def height(base: str = HTTP) -> int:
    return int(_json("GET", "/api/v1/status", base=base)["latestBlockNumber"])


def docker_exec(args: list[str], input_text: str | None = None,
                container: str = CONTAINER) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec", "-i", container, *args]
    return subprocess.run(cmd, input=input_text, text=True, capture_output=True, timeout=180)


def write_term(term: str, container: str = CONTAINER) -> str:
    path = f"/tmp/rcash-{uuid.uuid4().hex}.rho"
    proc = docker_exec(["sh", "-c", f"cat > {path}"], input_text=term, container=container)
    if proc.returncode != 0:
        raise DevnetError(f"could not write term: {proc.stderr.strip()}")
    return path


def deploy(term: str, secret: str, phlo_limit: int = 2_000_000, phlo_price: int = 1,
           container: str = CONTAINER, valid_after: int | None = None,
           base: str = HTTP) -> str:
    """Submit a signed deploy and return its deploy id (the deploy signature, hex)."""
    vabn = height(base) if valid_after is None else valid_after
    path = write_term(term, container)
    proc = docker_exec([
        "rnode", "--grpc-host", "localhost", "deploy",
        "--phlo-limit", str(phlo_limit), "--phlo-price", str(phlo_price),
        "--private-key", secret, "--shard-id", SHARD,
        "--valid-after-block-number", str(vabn), path,
    ], container=container)
    out = (proc.stdout or "") + (proc.stderr or "")
    match = DEPLOY_RE.search(out)
    if not match:
        # rnode prints a large jemalloc dump on exit; the useful error is before it.
        clean = out.split("___ Begin jemalloc statistics ___")[0].strip()
        lowered = clean.lower()
        if "429" in lowered:
            raise Refusal("429", clean[:2000])
        if "503" in lowered or "resource_exhausted" in lowered:
            raise Refusal("503", clean[:2000])
        if "duplicate" in lowered or "deploy pool is full" in lowered:
            raise Refusal("duplicate", clean[:2000])
        raise DevnetError(f"deploy failed (rc={proc.returncode}):\n{clean[:3000]}")
    return match.group(1)


def deploy_status(deploy_id: str, base: str = HTTP) -> dict:
    return _json("GET", f"/api/v1/deploy-status/{deploy_id}", base=base)


def _variant(doc: dict) -> tuple[str, dict]:
    for key, value in doc.items():
        if key.lower() in ("processedwithsuccess", "processedwitherror", "notprocessed"):
            return key.lower(), value
    return "unknown", {}


def wait_processed(deploy_id: str, timeout: float = 120.0, base: str = HTTP) -> tuple[str, dict]:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = deploy_status(deploy_id, base)
            variant, payload = _variant(last)
            if variant != "notprocessed" and variant != "unknown":
                return variant, payload
        except Refusal as e:
            if e.code not in ("429", "503", "transport"):
                raise
            last = {"error": str(e)}
        time.sleep(0.5)
    raise DevnetError(f"deploy {deploy_id} not processed within {timeout}s: {last}")


def deploy_result(deploy_id: str, timeout: float = 120.0, base: str = HTTP):
    variant, payload = wait_processed(deploy_id, timeout, base)
    if variant == "processedwithsuccess":
        return payload.get("deployResult")
    if variant == "processedwitherror":
        raise DevnetError(f"deploy errored: {payload.get('deployError')}")
    raise DevnetError(f"deploy {deploy_id}: {variant} {payload}")


def deploy_and_wait(term: str, secret: str, **kwargs):
    deploy_id = deploy(term, secret, **kwargs)
    return deploy_id, deploy_result(deploy_id, base=kwargs.get("base", HTTP))


def is_finalized(block_hash: str, base: str = HTTP) -> bool:
    try:
        return bool(_json("GET", f"/api/is-finalized/{block_hash}", base=base))
    except DevnetError:
        return bool(_json("GET", f"/api/v1/is-finalized/{block_hash}", base=base))


def wait_finalized(block_hash: str, timeout: float = 180.0, base: str = HTTP) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_finalized(block_hash, base):
            return True
        time.sleep(1.0)
    raise DevnetError(f"block {block_hash} not finalized within {timeout}s")


def block(block_hash: str, base: str = HTTP) -> dict:
    try:
        return _json("GET", f"/api/v1/block/{block_hash}", base=base)
    except DevnetError:
        return _json("GET", f"/api/block/{block_hash}", base=base)


def cost_of(deploy_id: str, base: str = HTTP) -> int | None:
    variant, payload = wait_processed(deploy_id, base=base)
    info = payload.get("block") or {}
    block_hash = info.get("blockHash")
    if not block_hash:
        return None
    doc = block(block_hash, base)
    for d in doc.get("deploys", []):
        if d.get("sig") == deploy_id:
            return d.get("cost")
    return None


def explore(term: str, base: str = HTTP):
    return _json("POST", "/api/v1/explore-deploy", body=term, base=base)


def explore_at(term: str, block_hash: str, base: str = HTTP, use_pre_state: bool = False):
    """Read state at a pinned block; the body must be camelCase."""
    return _json(
        "POST",
        "/api/v1/explore-deploy-by-block-hash",
        body={"term": term, "blockHash": block_hash, "usePreStateHash": use_pre_state},
        base=base,
    )


def data_at_name(name: str, block_hash: str = "", base: str = HTTP):
    body = {
        "name": {"ExprString": {"data": name}},
        "blockHash": block_hash,
        "usePreStateHash": False,
    }
    return _json("POST", "/api/v1/data-at-name-by-block-hash", body=body, base=base)


def faucet(address: str, base: str = HTTP):
    return _json("POST", "/api/v1/faucet", body={"address": address}, base=base)


def propose(base: str = ADMIN):
    return _json("POST", "/api/v1/propose", base=base, timeout=120)


def extract_strings(value) -> list[str]:
    """Collect every string/URI-ish leaf from a RhoExpr JSON reply (best effort)."""
    found: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("ExprString", "ExprUri") and isinstance(v, dict):
                found.append(str(v.get("data")))
            else:
                found.extend(extract_strings(v))
    elif isinstance(value, list):
        for v in value:
            found.extend(extract_strings(v))
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--container", default=CONTAINER)
    ap.add_argument("--http", default=HTTP)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("deploy", help="deploy a term file")
    d.add_argument("file")
    d.add_argument("--key", required=True, help="hex secret")
    d.add_argument("--phlo-limit", type=int, default=2_000_000)
    d.add_argument("--phlo-price", type=int, default=1)
    d.add_argument("--valid-after", type=int)

    s = sub.add_parser("status", help="deploy status")
    s.add_argument("deploy_id")

    e = sub.add_parser("explore", help="run a term without persisting")
    e.add_argument("file")

    r = sub.add_parser("read", help="data at a public name")
    r.add_argument("name")
    r.add_argument("--block", default="")

    c = sub.add_parser("cost", help="deploy cost in phlo")
    c.add_argument("deploy_id")

    sub.add_parser("height", help="current block height")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "deploy":
            term = Path(args.file).read_text()
            deploy_id = deploy(term, args.key, args.phlo_limit, args.phlo_price,
                               args.container, args.valid_after, args.http)
            print(deploy_id)
            variant, payload = wait_processed(deploy_id, base=args.http)
            print(json.dumps({variant: payload}, indent=2))
        elif args.cmd == "status":
            print(json.dumps(deploy_status(args.deploy_id, args.http), indent=2))
        elif args.cmd == "explore":
            print(json.dumps(explore(Path(args.file).read_text(), args.http), indent=2))
        elif args.cmd == "read":
            print(json.dumps(data_at_name(args.name, args.block, args.http), indent=2))
        elif args.cmd == "cost":
            print(cost_of(args.deploy_id, args.http))
        elif args.cmd == "height":
            print(height(args.http))
    except DevnetError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
