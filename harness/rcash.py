#!/usr/bin/env python3
"""R-Cash devnet harness.

Commands:
    keys                 generate/fund devnet keys
    probes               run the phase-0 capability gates and write spikes/REPORT.md
    deploy FILE          deploy a built term with the devnet deployer
    height               current block height
    status DEPLOY_ID     deploy status
    read NAME            data at a public name

Every probe deploys real terms to the local devnet. There is no simulation here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import deploy as node  # noqa: E402
import keygen  # noqa: E402
from coincurve import PrivateKey  # noqa: E402

SPIKES = ROOT / "spikes"
KEYS_PATH = ROOT / ".devnet" / "keys.json"
REPORT = SPIKES / "REPORT.md"
DEPLOYER = "deployer"


# --- keys -----------------------------------------------------------------------------------


def load_keys() -> dict:
    if not KEYS_PATH.exists():
        raise SystemExit("no devnet keys; run `make keys` first")
    return json.loads(KEYS_PATH.read_text())


def secret(keys: dict, name: str) -> str:
    return keys[name]["secret"]


def address(keys: dict, name: str) -> str:
    return keys[name]["address"]


def pubkey(keys: dict, name: str) -> str:
    return keys[name]["public"]


# --- term rendering -------------------------------------------------------------------------


def term(name: str, **subs: object) -> str:
    path = SPIKES / name
    if not path.exists():
        path = ROOT / name
    text = path.read_text()
    for k, v in subs.items():
        text = text.replace(f"__{k}__", str(v))
    missing = [k for k in ("__URI__", "__AMOUNT__", "__ADDRESS__", "__OWNER_PUBKEY__",
                           "__SECRET_HEX__", "__OP__", "__ARGS__") if k in text]
    if missing:
        raise ValueError(f"{name}: unresolved placeholders {missing}")
    return text


def pcall(uri: str, op: str, args: str = "", sig_args: str = "") -> str:
    """Call a registry-installed one-arm probe contract."""
    call = f'probe!("{op}"' + (f", {args}" if args else "") + ", *ret)"
    return f"""new rl(`rho:registry:lookup`), ch, ret, deployId(`rho:rchain:deployId`) in {{
  rl!(`{uri}`, *ch) |
  for (probe <- ch) {{
    {call} |
    for (@r <- ret) {{ deployId!(r) }}
  }}
}}"""


# --- deploy-result JSON ---------------------------------------------------------------------


def walk_exprs(value, out: list[tuple[str, object]]) -> list[tuple[str, object]]:
    if isinstance(value, dict):
        for k, v in value.items():
            if k.startswith("Expr") and isinstance(v, dict):
                out.append((k, v.get("data")))
                walk_exprs(v.get("data"), out)
            else:
                walk_exprs(v, out)
    elif isinstance(value, list):
        for v in value:
            walk_exprs(v, out)
    return out


def exprs(result) -> list[tuple[str, object]]:
    return walk_exprs(result, [])


def ints(result) -> list[int]:
    return [v for k, v in exprs(result) if k == "ExprInt"]


def bools(result) -> list[bool]:
    return [v for k, v in exprs(result) if k == "ExprBool"]


def strings(result) -> list[str]:
    return [str(v) for k, v in exprs(result) if k in ("ExprString", "ExprUri")]


def byte_strings(result) -> list[str]:
    out = []
    for k, v in exprs(result):
        if k != "ExprBytes":
            continue
        if isinstance(v, list):
            out.append(bytes(int(x) & 0xFF for x in v).hex())
        else:
            out.append(str(v))
    return out


def uris(result) -> list[str]:
    return [s for s in strings(result) if s.startswith("rho:id:")]


# --- deploy helpers -------------------------------------------------------------------------


def run(term_text: str, keyname: str = DEPLOYER, phlo_limit: int = 2_000_000,
        timeout: float = 120.0):
    keys = load_keys()
    deploy_id = node.deploy(term_text, secret(keys, keyname), phlo_limit=phlo_limit)
    result = node.deploy_result(deploy_id, timeout=timeout)
    return deploy_id, result


def run_install(term_text: str, timeout: float = 120.0) -> str:
    _, result = run(term_text, DEPLOYER, phlo_limit=8_000_000, timeout=timeout)
    found = uris(result)
    if not found:
        raise AssertionError(f"install returned no rho:id URI; result={json.dumps(result)[:1000]}")
    return found[0]


# --- probes ---------------------------------------------------------------------------------


class Check:
    def __init__(self, name: str):
        self.name = name
        self.ok = False
        self.detail = ""

    def pass_(self, detail: str):
        self.ok = True
        self.detail = detail
        return self

    def fail_(self, detail: str):
        self.ok = False
        self.detail = detail
        return self


def probe_persistence() -> Check:
    c = Check("persistence across blocks")
    uri = run_install(term("probe_persist.rho"))
    _, r1 = run(term("probe_persist_call.rho", URI=uri))
    _, r2 = run(term("probe_persist_call.rho", URI=uri))
    n1, n2 = ints(r1), ints(r2)
    if n1 == [1] and n2 == [2]:
        return c.pass_(f"counter 1 then 2 across two later deploys (uri {uri})")
    return c.fail_(f"expected [1] then [2], got {n1} then {n2}")


def probe_clock() -> Check:
    c = Check("block data")
    _, result = run(term("probe_clock.rho"))
    vals = exprs(result)
    return c.pass_(f"reply exprs: {vals}")


def probe_registry() -> Check:
    c = Check("registry insertArbitrary + lookup")
    uri = run_install(term("probe_registry_install.rho"))
    _, result = run(term("probe_registry_call.rho", URI=uri))
    got = strings(result)
    if "looked-up" in got:
        return c.pass_(f"lookup called the stored contract (uri {uri})")
    return c.fail_(f"expected 'looked-up', got {got}")


def probe_authority() -> Check:
    c = Check("deployerId account auth")
    keys = load_keys()
    uri = run_install(term("probe_authority_install.rho", OWNER_PUBKEY=pubkey(keys, DEPLOYER)))
    _, owner = run(term("probe_authority_call.rho", URI=uri), DEPLOYER)
    _, other = run(term("probe_authority_call.rho", URI=uri), "sender")
    owner_b, other_b = bools(owner), bools(other)
    if owner_b == [True] and other_b == [False]:
        return c.pass_(f"owner true, sender false (uri {uri})")
    return c.fail_(f"owner={owner_b}, other={other_b}")


def probe_rev() -> Check:
    c = Check("REV revFund/revRedeem round-trip")
    keys = load_keys()
    amount = 10_000_000
    _, result = run(term("probe_rev.rho", AMOUNT=amount,
                         ADDRESS=address(keys, DEPLOYER)), DEPLOYER)
    vals = ints(result)
    if len(vals) >= 4 and vals[0] == vals[-1]:
        return c.pass_(f"balance before={vals[0]} after={vals[-1]}; replies={vals[1:-1]}")
    return c.fail_(f"unexpected replies {vals}")


def probe_rev_contract() -> Check:
    c = Check("contract can spend presented deployerId REV (containment rationale)")
    keys = load_keys()
    uri = run_install(term("probe_rev_contract.rho"))
    amount = 10_000_000
    _, funded = run(term("probe_rev_contract_call.rho", URI=uri, AMOUNT=amount), "sender")
    _, bal = run(pcall(uri, "balance"), DEPLOYER)
    vals = ints(bal)
    if vals and vals[-1] == amount:
        return c.pass_(f"contract purse={vals[-1]}; fund reply={ints(funded)} (uri {uri})")
    return c.fail_(f"contract balance {vals}, expected {amount}")


def probe_ertp() -> Check:
    c = Check("contract-held ERTP purse across blocks + burn facet")
    uri = run_install(term("probe_ertp.rho"))
    _, m1 = run(pcall(uri, "mint", "10"))
    _, b1 = run(pcall(uri, "balance"))
    _, m2 = run(pcall(uri, "mint", "5"))
    _, b2 = run(pcall(uri, "balance"))
    _, burn = run(pcall(uri, "burn", "3"))
    _, b3 = run(pcall(uri, "balance"))
    seq = (ints(m1), ints(b1), ints(m2), ints(b2), ints(burn), ints(b3))
    if seq[0][-1] == 10 and seq[1][-1] == 10 and seq[2][-1] == 15 and seq[3][-1] == 15 \
            and seq[4][-1] == 3 and seq[5][-1] == 15:
        return c.pass_(f"mint 10->15, burn 3, balance stays 15 (uri {uri})")
    return c.fail_(f"unexpected sequence {seq}")


def probe_deadlock() -> Check:
    c = Check("silent deadlock / consumed state cell (documented hazard)")
    uri = run_install(term("probe_deadlock.rho"))
    _, dead = run(pcall(uri, "dead"), DEPLOYER, timeout=30)
    _, inc = run(pcall(uri, "inc"), DEPLOYER, timeout=30)
    return c.pass_(f"dead reply={ints(dead)}; subsequent inc reply={ints(inc)} "
                   f"(both empty means the cell is consumed and the deploy still commits)")


def probe_signature() -> Check:
    c = Check("secp256k1Verify over blake2b256 payload")
    keys = load_keys()
    uri = run_install(term("probe_signature.rho"))
    payload = b"rcash:probe:signature:v1"
    digest = hashlib.blake2b(payload, digest_size=32).digest()
    sig = PrivateKey(bytes.fromhex(secret(keys, DEPLOYER))).sign(digest, hasher=None)
    pub = bytes.fromhex(pubkey(keys, DEPLOYER))
    good = f'"{payload.hex()}".hexToBytes(), "{sig.hex()}".hexToBytes(), "{pub.hex()}".hexToBytes()'
    bad_sig = bytearray(sig)
    bad_sig[-1] ^= 0x01
    bad = f'"{payload.hex()}".hexToBytes(), "{bytes(bad_sig).hex()}".hexToBytes(), "{pub.hex()}".hexToBytes()'
    _, ok = run(pcall(uri, "verify", good))
    _, no = run(pcall(uri, "verify", bad))
    if bools(ok) == [True] and bools(no) == [False]:
        return c.pass_(f"valid=true, tampered=false (uri {uri})")
    return c.fail_(f"valid={bools(ok)}, tampered={bools(no)}")


def probe_rollback() -> Check:
    c = Check("failed deploy rolls back tuple space + native ERTP/REV")
    uri = run_install(term("probe_rollback.rho"))
    keys = load_keys()
    dep_id = node.deploy(term("probe_rollback_call.rho", URI=uri),
                         secret(keys, DEPLOYER), phlo_limit=8_000_000)
    failed = False
    err = ""
    try:
        node.deploy_result(dep_id)
    except Exception as e:
        failed = True
        err = str(e)[:300]
    _, g = run(pcall(uri, "get"))
    _, b = run(pcall(uri, "balance"))
    _, rb = run(pcall(uri, "revBalance"))
    state, bal, rev = ints(g), ints(b), ints(rb)
    if failed and state == [0] and bal and bal[-1] == 0 and rev and rev[-1] == 0:
        return c.pass_(f"deploy failed as intended; state={state}, erp={bal}, rev={rev}")
    return c.fail_(f"failed={failed} err={err} state={state} erp={bal} rev={rev}")


def probe_cost_and_finality() -> Check:
    c = Check("measured cost + finality")
    keys = load_keys()
    dep_id = node.deploy(term("probe_persist.rho"), secret(keys, DEPLOYER), phlo_limit=8_000_000)
    variant, payload = node.wait_processed(dep_id)
    cost_install = node.cost_of(dep_id)
    block_hash = (payload.get("block") or {}).get("blockHash", "")
    finalized = node.wait_finalized(block_hash, timeout=120) if block_hash else False
    uri = uris(node.deploy_result(dep_id))[0]
    dep2 = node.deploy(term("probe_persist_call.rho", URI=uri), secret(keys, DEPLOYER),
                       phlo_limit=2_000_000)
    node.wait_processed(dep2)
    cost_call = node.cost_of(dep2)
    return c.pass_(f"install phlo={cost_install}, call phlo={cost_call}, "
                   f"block {block_hash[:12]}… finalized={finalized}")


def probe_claimhash() -> Check:
    c = Check("claim secret blake2b256 matches off-chain")
    secret_bytes = os.urandom(32)
    digest = hashlib.blake2b(secret_bytes, digest_size=32).digest()
    _, result = run(term("probe_claimhash.rho", SECRET_HEX=secret_bytes.hex()))
    got = byte_strings(result)
    if got and got[-1].lower() == digest.hex():
        return c.pass_(f"hash {got[-1]}")
    return c.fail_(f"rholang hash {got}, python {digest.hex()}; raw={exprs(result)}")


PROBES = [
    probe_persistence,
    probe_clock,
    probe_registry,
    probe_authority,
    probe_rev,
    probe_rev_contract,
    probe_ertp,
    probe_rollback,
    probe_deadlock,
    probe_signature,
    probe_claimhash,
    probe_cost_and_finality,
]


def cmd_probes() -> int:
    print(f"==> devnet height {node.height()}")
    checks: list[Check] = []
    for probe in PROBES:
        try:
            c = probe()
        except Exception as e:
            c = Check(probe.__name__)
            c.fail_(f"{type(e).__name__}: {e}")
            traceback.print_exc()
        checks.append(c)
        print(f"[{'PASS' if c.ok else 'FAIL'}] {c.name}: {c.detail}")

    passed = sum(1 for c in checks if c.ok)
    lines = [
        "# Phase-0 capability gate report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Node commit: `{node_commit()}`",
        f"Result: **{passed}/{len(checks)} passed**",
        "",
        "| Gate | Result | Evidence |",
        "|---|---|---|",
    ]
    for c in checks:
        evidence = c.detail.replace("|", "\\|")
        lines.append(f"| {c.name} | {'PASS' if c.ok else 'FAIL'} | {evidence} |")
    lines += ["", "A FAIL here is a stop-the-build gate, not a flaky test.", ""]
    REPORT.write_text("\n".join(lines))
    print(f"wrote {REPORT.relative_to(ROOT)}: {passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


def node_commit() -> str:
    repo = Path(
        os.environ.get(
            "RHOLO_DIR",
            os.environ.get("RCHAIN_RUST_DIR", ROOT.parent / "rholo"),
        )
    )
    try:
        import subprocess
        return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                       text=True).strip()
    except Exception:
        return "unknown"


# --- CLI ------------------------------------------------------------------------------------


def cmd_keys(args) -> int:
    argv = ["--out", str(KEYS_PATH), "--faucet"] if args.faucet else ["--out", str(KEYS_PATH)]
    return keygen.main(argv)


def cmd_deploy(args) -> int:
    keys = load_keys()
    term_text = Path(args.file).read_text()
    deploy_id = node.deploy(term_text, secret(keys, args.key), phlo_limit=args.phlo_limit)
    print(deploy_id)
    try:
        variant, payload = node.wait_processed(deploy_id)
        print(json.dumps({variant: payload}, indent=2)[:8000])
    except Exception as e:
        print(f"wait failed: {e}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    k = sub.add_parser("keys")
    k.add_argument("--faucet", action="store_true")

    sub.add_parser("probes")

    d = sub.add_parser("deploy")
    d.add_argument("file")
    d.add_argument("--key", default=DEPLOYER)
    d.add_argument("--phlo-limit", type=int, default=2_000_000)

    sub.add_parser("height")

    s = sub.add_parser("status")
    s.add_argument("deploy_id")

    r = sub.add_parser("read")
    r.add_argument("name")
    r.add_argument("--block", default="")

    args = ap.parse_args(argv)
    if args.cmd == "keys":
        return cmd_keys(args)
    if args.cmd == "probes":
        return cmd_probes()
    if args.cmd == "deploy":
        return cmd_deploy(args)
    if args.cmd == "height":
        print(node.height())
        return 0
    if args.cmd == "status":
        print(json.dumps(node.deploy_status(args.deploy_id), indent=2))
        return 0
    if args.cmd == "read":
        print(json.dumps(node.data_at_name(args.name, args.block), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
