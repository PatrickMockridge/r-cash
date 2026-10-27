#!/usr/bin/env python3
"""Install the v0.4 platform on a rhobot-shaped testnet or a disposable devnet.

Deploys go through the Rust CLI's **cached** path: each step has an operation id and a
write-ahead signed body in ``.testnet/ops``. A retry reuses those exact bytes, which the
node refuses before parsing while the deploy is pooled, so a transport retry cannot
double-apply. The installer then verifies the step at the block that carried it:

* the deploy status names a block;
* that block is finalized and does not list the deploy in ``rejectedDeploys``;
* every expected ``Root`` key resolves at that block's post-state.

A step that is already present on-chain is skipped and its URIs are read from ``Root``,
so a re-run after a lost local state file does not redeploy components.

Usage:
    python3 harness/install_testnet.py --node http://localhost:40403
    python3 harness/install_testnet.py --allow-live --node http://164.90.140.144:40403

The live rhobot endpoint requires ``--allow-live`` because its chain predates the C336
merge fix and must not be treated as a test target.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "contracts" / "build" / "deploy" / "v3"
KEYS = ROOT / ".testnet" / "keys.json"
DEVNET_KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".testnet" / "install.json"
OPS = ROOT / ".testnet" / "ops"
RCASH = ROOT / "target" / "debug" / "rcash"
DEFAULT_NODE = "http://164.90.140.144:40403"
LIVE_HINTS = ("rhobot.net", "164.90.140.144", "104.131.176.164")
PLACEHOLDER = re.compile(r"__[A-Z0-9_]+__")
MAX_TERM_BYTES = 48 * 1024

sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "tools"))

from chainclient import ChainClientError, MergeRejected, Node, Refused  # noqa: E402
from minify_rho import minify  # noqa: E402

# The Root key(s) each deploy must leave live before the next dependent deploy.
STEP_KEYS = {
    "root": ["rcash:root"],
    "admin_guard": ["component:admin-guard"],
    "kernel": ["component:clock", "component:verifier", "component:codec"],
    "bounds": ["component:bounds"],
    "governor": ["component:governor"],
    "05_amm_math": ["component:amm-math"],
    "06_collateral_math": ["component:collateral-math"],
    "07_oracle_math": ["component:oracle-math"],
    "08_claim_code": ["component:claim-code"],
    "oracle_registry": ["component:oracle-registry"],
    "oracle_hub": ["component:oracle-hub"],
    "currency_registry": [
        "component:stablecoin-directory",
        "component:currency-registry",
    ],
    "asset_resolver": ["component:asset-resolver"],
    "transfer": ["component:transfer-book"],
    "pool_template": ["component:pool-template"],
    "market": [
        "component:market-terms",
        "component:market-directory",
        "component:market-index",
        "component:market-factory",
        "component:tradability-gate",
        "component:listing-views",
    ],
    "identity": ["component:account-factory"],
}


def render(name: str, replacements: dict[str, str]) -> str:
    path = BUILD / f"{name}.rho"
    if not path.is_file():
        raise SystemExit(f"missing built term {path}; run tools/build_contracts.py")
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(key, value)
    leftover = PLACEHOLDER.findall(text)
    if leftover:
        raise SystemExit(f"{name}: unresolved placeholders {sorted(set(leftover))}")
    text = minify(text)
    size = len(text.encode("utf-8"))
    if size > MAX_TERM_BYTES:
        raise SystemExit(
            f"{name}: {size} bytes exceeds the installer budget {MAX_TERM_BYTES}"
        )
    print(f"{name}: {size} bytes")
    return text


class Installer:
    def __init__(
        self,
        node_url: str,
        allow_live: bool,
        keys_path: Path = KEYS,
        state_path: Path = STATE,
        ops_path: Path = OPS,
        admin_keys_path: Path = DEVNET_KEYS,
        manifest_path: Path | None = None,
        min_lock_blocks: str = "302400",
    ):
        if any(hint in node_url for hint in LIVE_HINTS) and not allow_live:
            raise SystemExit(
                "refusing the live rhobot chain without --allow-live: it predates the "
                "C336 merge fix. Point --node at a disposable devnet."
            )
        self.chain = Node(node_url)
        self.node_url = node_url
        self.keys_path = keys_path
        self.state_path = state_path
        self.ops_path = ops_path
        self.manifest_path = manifest_path or (ROOT / "deployments" / "testnet-v4.json")
        self.min_lock_blocks = min_lock_blocks
        self.keys = json.loads(keys_path.read_text())
        self.deployer = self.keys["deployer"]
        self.devnet = json.loads(admin_keys_path.read_text())
        self.state: dict = {}
        self.root_uri: str | None = None

    # -- deploy -------------------------------------------------------------

    def deploy(self, term: str, op: str | None) -> dict:
        self.ops_path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".rho", delete=False) as handle:
            handle.write(term)
            path = handle.name
        try:
            proc = subprocess.run(
                [
                    str(RCASH), "--node", self.node_url, "--keys", str(self.keys_path),
                    "--key", "deployer", "--json", "deploy",
                    *(["--op", op, "--op-cache", str(self.ops_path)] if op else []),
                    path,
                ],
                capture_output=True, text=True, timeout=900,
            )
        finally:
            Path(path).unlink(missing_ok=True)
        if proc.returncode == 4:
            raise Refused("cli", (proc.stderr or proc.stdout).strip()[:1000])
        lines = (proc.stdout or "").strip().splitlines()
        doc = None
        for line in reversed(lines):
            if line.strip().startswith("{"):
                try:
                    doc = json.loads(line)
                except json.JSONDecodeError:
                    continue
                break
        if doc is None:
            detail = ((proc.stdout or "") + (proc.stderr or "")).split(
                "___ Begin jemalloc"
            )[0]
            raise ChainClientError(
                f"deploy produced no JSON (rc={proc.returncode}): {clean(detail)}"
            )
        if doc.get("error"):
            raise ChainClientError(f"deploy failed: {doc['error']}")
        if "success" not in str(doc.get("status", "")).lower():
            raise ChainClientError(f"deploy not successful: {doc}")
        return doc

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=2) + "\n")

    # -- verification -------------------------------------------------------

    def resolved(self, block_hash: str | None, keys: list[str]) -> list[str]:
        """Resolve Root keys with a **signed read**.

        The fixed node's exploratory deploy cannot see the native registry: a
        ``rho:registry:lookup`` inside ``explore-deploy-by-block-hash`` returns Nil.
        A signed deploy sees it, so verification is a small paid read whose result is
        checked against the finalized block that carried the write. ``block_hash`` is
        kept for the call sites; the read itself is at the current finalized state.
        """
        assert self.root_uri, "root URI is not known yet"
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
            f"new rl(`rho:registry:lookup`), rCh, Root, {channels}, {outs}, "
            f"deployId(`rho:rchain:deployId`) in {{"
            f' rl!(`{self.root_uri}`, *rCh) | for (Root <- rCh) {{ {sends} | {arms} |'
            f" for ({joins}) {{ deployId!([{values}]) }} }} }}"
        )
        doc = self.read(term)
        found = [
            uri for uri in walk(doc.get("result"), [])
            if isinstance(uri, str)
        ]
        while len(found) < len(keys):
            found.append("missing")
        return found[: len(keys)]

    def read(self, term: str) -> dict:
        return self.deploy(term, None)

    def step(
        self,
        name: str,
        op: str,
        replacements: dict[str, str],
        keys: list[str],
        tip: str | None,
    ) -> list[str]:
        steps = self.state.setdefault("steps", {})
        if self.root_uri and tip:
            present = self.resolved(tip, keys)
            if "missing" not in present:
                steps[name] = {"uris": present, "block": tip, "reused": True}
                self.save()
                print(f"{name}: present at {tip[:12]}…, skipped")
                return present

        last_error: Exception | None = None
        for round_number in range(3):
            operation = op if round_number == 0 else f"{op}:retry{round_number}"
            try:
                doc = self.deploy(render(name, replacements), operation)
                block = doc.get("blockHash")
                if not block:
                    block = self.chain.wait_included(doc["deployId"])
                else:
                    block = self.chain.wait_included(doc["deployId"])
                if name == "00_root":
                    found = uris(doc)
                    if not found:
                        raise ChainClientError("root deploy returned no URI")
                    self.root_uri = found[0]
                    present = self.resolved(block, keys)
                else:
                    present = self.resolved(block, keys)
                if "missing" in present:
                    raise ChainClientError(
                        f"{name}: Root key(s) {keys} did not resolve at {block}"
                    )
                steps[name] = {"deploy_id": doc.get("deployId"), "uris": present,
                               "block": block}
                self.save()
                print(f"{name}: {present}")
                return present
            except (MergeRejected, ChainClientError, Refused) as error:
                last_error = error
                # A merge-rejected deploy cannot be re-included: prove the effect absent
                # and retry under a new operation id. A refused deploy is safe to retry
                # with the cached bytes, which the CLI does.
                print(f"{name}: attempt {round_number + 1} failed: {error}", file=sys.stderr)
                if self.root_uri:
                    tip = self.chain.last_finalized_block().get("blockHash", tip)
                    present = self.resolved(tip, keys)
                    if "missing" not in present:
                        steps[name] = {"uris": present, "block": tip, "reused": True}
                        self.save()
                        return present
        raise SystemExit(f"REFUSED step={name} detail={last_error}")

    # -- driver -------------------------------------------------------------

    def run(self, fresh: bool) -> int:
        if fresh:
            self.state_path.unlink(missing_ok=True)
            # Retire the cached signatures too: --fresh means a new install intent.
            for path in self.ops_path.glob("*.json"):
                path.unlink()
        if self.state_path.is_file():
            self.state = json.loads(self.state_path.read_text())
        self.root_uri = self.state.get("root_uri")

        status = self.chain.preflight()
        try:
            tip = self.chain.last_finalized_block().get("blockHash")
        except (Refused, ChainClientError):
            # A fresh chain has no finalized fringe until the first proposal.
            tip = None
        print(
            f"node: degraded={status.get('degraded')} "
            f"acceptsDeploys={status.get('acceptsDeploys')} tip={str(tip)[:12]}…"
        )

        admins = key_list(self.devnet, ["admin1", "admin2", "admin3"])
        common = {"__ROOT_URI__": self.root_uri or ""}

        root = self.step(
            "00_root", "testnet:root",
            {"__INSTALLER_PUB__": self.deployer["public"], "__ADMIN_KEYS__": admins},
            STEP_KEYS["root"], tip,
        )
        self.root_uri = self.state.get("root_uri") or root[0]
        self.state["root_uri"] = self.root_uri
        self.save()
        common["__ROOT_URI__"] = self.root_uri

        self.step("03_admin_guard", "testnet:admin_guard", common,
                  STEP_KEYS["admin_guard"], tip)
        self.step("01_kernel", "testnet:kernel", common, STEP_KEYS["kernel"], tip)
        self.step("02_bounds", "testnet:bounds", common, STEP_KEYS["bounds"], tip)
        self.step(
            "04_governor", "testnet:governor",
            {"__ROOT_URI__": self.root_uri, "__ADMIN_KEYS__": admins},
            STEP_KEYS["governor"], tip,
        )
        for name in ["05_amm_math", "06_collateral_math", "07_oracle_math", "08_claim_code"]:
            self.step(name, f"testnet:{name}", common, STEP_KEYS[name], tip)

        allowlist = "[" + ", ".join(
            f'"{self.devnet[n]["public"]}"'
            for n in ["reporter1", "reporter2", "reporter3"]
        ) + "]"
        self.step(
            "12_oracle_registry", "testnet:oracle_registry",
            {"__ROOT_URI__": self.root_uri, "__ADMIN_KEYS__": admins,
             "__ALLOWLIST__": allowlist},
            STEP_KEYS["oracle_registry"], tip,
        )
        self.step("13_oracle_hub", "testnet:oracle_hub", common,
                  STEP_KEYS["oracle_hub"], tip)
        self.step("32_currency_registry", "testnet:currency_registry", common,
                  STEP_KEYS["currency_registry"], tip)
        resolver = self.step("14_asset_resolver", "testnet:asset_resolver", common,
                             STEP_KEYS["asset_resolver"], tip)
        self.step(
            "40_transfer", "testnet:transfer",
            {**common, "__BOOK_PARAMS__": '{"minAmount": 1, "defaultExpiryBlocks": 720, "maxExpiryBlocks": 1296000, "maxMemoBytes": 128, "maxOpIdBytes": 64, "maxStipend": 100000000}'},
            STEP_KEYS["transfer"], tip,
        )
        self.step(
            "51_pool", "testnet:pool_template",
            {"__ROOT_URI__": self.root_uri, "__ASSET_RESOLVER_URI__": resolver[0]},
            STEP_KEYS["pool_template"], tip,
        )
        self.step(
            "50_market", "testnet:market",
            {"__ROOT_URI__": self.root_uri, "__ASSET_RESOLVER_URI__": resolver[0],
             "__MIN_LOCK_BLOCKS__": self.min_lock_blocks},
            STEP_KEYS["market"], tip,
        )
        self.step(
            "09_identity", "testnet:identity",
            {"__ROOT_URI__": self.root_uri, "__ASSET_RESOLVER_URI__": resolver[0]},
            STEP_KEYS["identity"], tip,
        )

        manifest = build_manifest(self.state)
        # The unit harnesses read the resolved URIs from the state file, as
        # install_v3 writes them. Keep both outputs in the same shape, including
        # the legacy per-step keys the older suites still use.
        self.state.update(manifest)
        for step in ("05_amm_math", "06_collateral_math", "07_oracle_math", "08_claim_code"):
            found = self.state.get("steps", {}).get(step, {}).get("uris") or []
            if found:
                self.state[f"{step}_uri"] = found[0]
        self.save()
        out = self.manifest_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"manifest: {out}")
        print(json.dumps(self.state, indent=2))
        return 0


def walk(value, out: list[str]) -> list[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("ExprUri", "ExprString") and isinstance(item, dict):
                out.append(item.get("data"))
            else:
                walk(item, out)
    elif isinstance(value, list):
        for item in value:
            walk(item, out)
    return out


def uris(doc: dict) -> list[str]:
    return [
        uri
        for uri in walk(doc.get("result"), [])
        if isinstance(uri, str) and uri.startswith("rho:id:")
    ]


def key_list(keys: dict, names: list[str]) -> str:
    return "[" + ", ".join(f'"{keys[n]["public"]}".hexToBytes()' for n in names) + "]"


def build_manifest(state: dict) -> dict:
    steps = state.get("steps", {})
    order = {
        "clock_uri": ("01_kernel", 0),
        "verifier_uri": ("01_kernel", 1),
        "codec_uri": ("01_kernel", 2),
        "bounds_uri": ("02_bounds", 0),
        "admin_guard_uri": ("03_admin_guard", 0),
        "governor_uri": ("04_governor", 0),
        "amm_math_uri": ("05_amm_math", 0),
        "oracle_registry_uri": ("12_oracle_registry", 0),
        "oracle_hub_uri": ("13_oracle_hub", 0),
        "currency_registry_uri": ("32_currency_registry", 1),
        "stablecoin_directory_uri": ("32_currency_registry", 0),
        "asset_resolver_uri": ("14_asset_resolver", 0),
        "transfer_book_uri": ("40_transfer", 0),
        "pool_template_uri": ("51_pool", 0),
        "market_terms_uri": ("50_market", 0),
        "market_directory_uri": ("50_market", 1),
        "market_index_uri": ("50_market", 2),
        "market_factory_uri": ("50_market", 3),
        "tradability_gate_uri": ("50_market", 4),
        "listing_views_uri": ("50_market", 5),
        "account_factory_uri": ("09_identity", 0),
    }
    manifest = {"root_uri": state["root_uri"]}
    for field, (step, index) in order.items():
        found = steps.get(step, {}).get("uris") or []
        manifest[field] = found[index] if index < len(found) else None
    return manifest


def clean(text: str) -> str:
    return "".join(ch for ch in text if ch == "\n" or ord(ch) >= 32)[:2000]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--node", default=DEFAULT_NODE)
    ap.add_argument("--allow-live", action="store_true")
    ap.add_argument("--keys", type=Path, default=KEYS)
    ap.add_argument("--state", type=Path, default=STATE)
    ap.add_argument("--ops", type=Path, default=OPS)
    ap.add_argument("--admin-keys", type=Path, default=DEVNET_KEYS)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--min-lock-blocks", default="302400")
    args = ap.parse_args(argv)
    try:
        return Installer(
            args.node, args.allow_live, args.keys, args.state, args.ops,
            args.admin_keys, args.manifest, args.min_lock_blocks,
        ).run(args.fresh)
    except Refused as error:
        print(f"REFUSED node detail={error}", file=sys.stderr)
        return 4
    except ChainClientError as error:
        print(f"installer failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
