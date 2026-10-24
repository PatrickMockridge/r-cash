#!/usr/bin/env python3
"""Refusal-aware rholo client shared by the installers and the merge arms.

The node now has designed refusals: 429, 503 with ``Retry-After``, gRPC
``RESOURCE_EXHAUSTED``, duplicate deploys, and a deploy pool bounded by term bytes.
A deploy that returns HTTP 200 is only *submitted*; inclusion is a separate claim
(``deploy-status`` names a block, the block must be finalized, and the block's
``rejectedDeploys`` must not name the deploy).

This module classifies each outcome, retries only what is safe to retry with bounded
exponential backoff and jitter, and verifies a postcondition at a pinned block.
It is standard-library only so it runs on the devnet host and inside the merge arms.
"""

from __future__ import annotations

import json
import random
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class ChainClientError(RuntimeError):
    """A non-retryable protocol or verification failure."""


class Refused(ChainClientError):
    """The node refused the work. ``code`` is what a script branches on."""

    def __init__(self, code: str, detail: str, retry_after: int | None = None):
        super().__init__(f"REFUSED code={code} retry_after={retry_after or 0} detail={detail}")
        self.code = code
        self.detail = detail
        self.retry_after = retry_after


class MergeRejected(ChainClientError):
    """The deploy was processed in a branch but a merge rejected it."""


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: str

    def json(self) -> Any:
        return json.loads(self.body)


class Node:
    """One node's public HTTP API, optionally reached with ``docker exec``.

    ``container`` is for a partitioned devnet node that is off the host bridge; the
    request then runs ``curl`` inside that container.
    """

    def __init__(
        self,
        base: str = "http://localhost:40403",
        container: str | None = None,
        attempts: int = 8,
        timeout: float = 30.0,
    ):
        self.base = base.rstrip("/")
        self.container = container
        self.attempts = attempts
        self.timeout = timeout

    # -- transport ---------------------------------------------------------

    def _once(self, method: str, path: str, body: str | None) -> Response:
        url = f"{self.base}{path}"
        if self.container:
            command = [
                "docker", "exec", self.container, "curl", "-sS", "-X", method,
                "-w", "\n%{http_code}", url,
            ]
            if body is not None:
                command += ["-H", "content-type: application/json", "--data-binary", body]
            proc = subprocess.run(
                command, capture_output=True, text=True, timeout=self.timeout
            )
            if proc.returncode != 0:
                raise ConnectionError(proc.stderr.strip() or "curl failed")
            text = proc.stdout
            payload, _, status_text = text.rpartition("\n")
            try:
                status = int(status_text.strip())
            except ValueError:
                status, payload = 200, text
            return Response(status, {}, payload)

        data = body.encode() if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"content-type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return Response(
                    response.status,
                    {k.lower(): v for k, v in response.headers.items()},
                    response.read().decode(),
                )
        except urllib.error.HTTPError as error:
            headers = {k.lower(): v for k, v in (error.headers or {}).items()}
            return Response(
                error.code, headers, error.read().decode(errors="replace")
            )

    def request(self, method: str, path: str, body: str | None = None) -> Response:
        """Send, retrying only the designed transient refusals."""
        last: str = "no attempt"
        for attempt in range(self.attempts):
            retry_after = None
            try:
                response = self._once(method, path, body)
            except (ConnectionError, TimeoutError, OSError) as error:
                last = str(error)
            else:
                if response.status < 300:
                    return response
                if response.status == 429:
                    retry_after = _int_header(response.headers, "retry-after")
                    last = f"429 {response.body[:200]}"
                elif response.status == 503:
                    retry_after = _int_header(response.headers, "retry-after")
                    last = f"503 {response.body[:200]}"
                elif response.status in (408, 425):
                    retry_after = None
                    last = f"{response.status} {response.body[:200]}"
                else:
                    raise Refused(str(response.status), response.body[:1000])
            delay = _backoff(attempt)
            if retry_after:
                delay = max(delay, float(retry_after))
            time.sleep(delay)
        raise Refused("exhausted", last)

    # -- reads -------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return self.request("GET", "/api/v1/status").json()

    def admission(self) -> dict[str, Any]:
        return self.request("GET", "/api/v1/admission").json()

    def preflight(self) -> dict[str, Any]:
        """Refuse to start when the node says it will not accept deploys."""
        status = self.status()
        if status.get("acceptsDeploys") is False:
            raise Refused(
                "admission",
                f"acceptsDeploys=false degraded={status.get('degraded')}",
            )
        return status

    def deploy_status(self, deploy_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/deploy-status/{deploy_id}").json()

    def block(self, block_hash: str) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/block/{block_hash}").json()

    def last_finalized_block(self) -> dict[str, Any]:
        value = self.request("GET", "/api/last-finalized-block").json()
        return value.get("blockInfo", value)

    def is_finalized(self, block_hash: str) -> bool:
        return bool(self.request("GET", f"/api/is-finalized/{block_hash}").json())

    def explore_at(self, term: str, block_hash: str, use_pre_state: bool = False) -> dict[str, Any]:
        body = json.dumps(
            {
                "term": term,
                "blockHash": block_hash,
                "usePreStateHash": use_pre_state,
            }
        )
        return self.request(
            "POST", "/api/v1/explore-deploy-by-block-hash", body
        ).json()

    # -- verification ------------------------------------------------------

    def wait_included(
        self,
        deploy_id: str,
        attempts: int = 120,
        delay: float = 0.5,
    ) -> str:
        """Return the finalized block hash that carries the deploy.

        A ``ProcessedWithSuccess`` status is not enough: a merge can reject the
        deploy wholesale, and the deploy's own status stays successful. The block
        must be finalized and must not list the deploy in ``rejectedDeploys``.
        """
        last = "no status"
        deadline = time.time() + attempts * delay * 4
        while time.time() < deadline:
            status = self.deploy_status(deploy_id)
            if "ProcessedWithSuccess" in status:
                info = status["ProcessedWithSuccess"]
                block_hash = _block_hash(info.get("block"))
                if not block_hash:
                    raise ChainClientError("deploy status has no block hash")
                block = self.block(block_hash)
                rejected = _rejected(block)
                if deploy_id.lower() in {item.lower() for item in rejected}:
                    raise MergeRejected(
                        f"deploy {deploy_id} is in {block_hash} rejectedDeploys"
                    )
                if self.is_finalized(block_hash):
                    return block_hash
                last = f"block {block_hash} not finalized"
            elif "ProcessedWithError" in status:
                raise ChainClientError(
                    f"deploy {deploy_id} failed: "
                    f"{status['ProcessedWithError'].get('deployError')}"
                )
            else:
                last = json.dumps(status)[:200]
            time.sleep(delay)
            delay = min(delay * 1.5, 8.0)
        raise ChainClientError(f"deploy {deploy_id} not included: {last}")

    def root_keys(self, root_uri: str, block_hash: str) -> list[str]:
        """Read ``Root.keys`` at a block's post-state."""
        term = (
            "new rl(`rho:registry:lookup`), rCh, Root, out in {"
            " rl!(`" + root_uri + "`, *rCh) |"
            " for (Root <- rCh) { Root!(\"keys\", *out) } }"
        )
        response = self.explore_at(term, block_hash)
        return _strings(response)

    def root_resolve_many(
        self, root_uri: str, keys: list[str], block_hash: str
    ) -> list[str]:
        """Resolve several component keys in one read. A missing key yields ``missing``."""
        channels = ", ".join(f"c{i}" for i in range(len(keys)))
        outs = ", ".join(f"o{i}" for i in range(len(keys)))
        sends = " | ".join(
            f'Root!("resolve", "{key}", 1, *c{i})' for i, key in enumerate(keys)
        )
        arms = " | ".join(
            f'for (@a{i} <- c{i}) {{ match a{i} {{ (true, u, _) => o{i}!(u)\n _ => o{i}!("missing") }} }}'
            for i in range(len(keys))
        )
        joins = "; ".join(f"@u{i} <- o{i}" for i in range(len(keys)))
        values = ", ".join(f"u{i}" for i in range(len(keys)))
        term = (
            f"new rl(`rho:registry:lookup`), rCh, Root, out, {channels}, {outs} in {{"
            f' rl!(`{root_uri}`, *rCh) | for (Root <- rCh) {{ {sends} | {arms} |'
            f" for ({joins}) {{ out!([{values}]) }} }} }}"
        )
        response = self.explore_at(term, block_hash)
        values = _strings(response)
        # An unresolved key produces no reply at all; make that explicit.
        while len(values) < len(keys):
            values.append("missing")
        return values[: len(keys)]


# -- helpers ----------------------------------------------------------------


def _block_hash(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("blockHash", "block_hash"):
            if isinstance(value.get(key), str):
                return value[key]
    return None


def _rejected(block: dict[str, Any]) -> list[str]:
    for container in (block, block.get("blockInfo"), block.get("block")):
        if isinstance(container, dict):
            for key in ("rejectedDeploys", "rejected_deploys"):
                value = container.get(key)
                if isinstance(value, list):
                    return [str(item) for item in value]
    return []


def _strings(value: Any) -> list[str]:
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                if key in ("ExprString", "ExprUri") and isinstance(item, dict):
                    out.append(str(item.get("data")))
                else:
                    walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return out


def _int_header(headers: dict[str, str], name: str) -> int | None:
    raw = headers.get(name)
    if not raw:
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


def _backoff(attempt: int) -> float:
    base = min(0.25 * (2**attempt), 8.0)
    return base / 2 + random.uniform(0, base / 2)
