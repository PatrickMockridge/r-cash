#!/usr/bin/env python3
"""Phase-4b: send a claimable NGN->KES transfer, claim it, and refund an expired one."""
from __future__ import annotations
import hashlib, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "harness" / "scenarios"))
import deploy as node  # noqa: E402
import oracle  # noqa: E402
import vault as v  # noqa: E402

MANIFEST = ROOT / "deployments" / "devnet.json"; KEYS = ROOT / ".devnet" / "keys.json"

def run_as(term, key="deployer", phlo=30_000_000):
    keys = json.loads(KEYS.read_text())
    did = node.deploy(term, keys[key]["secret"], phlo_limit=phlo)
    return node.deploy_result(did, timeout=240)

def main() -> int:
    manifest = json.loads(MANIFEST.read_text()); v.manifest = manifest; oracle.manifest = manifest
    factory = manifest["account_factory_uri"]
    checks = []
    def check(name, ok, detail=""):
        checks.append((name, ok, detail)); print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    h = node.height()
    for cur, price in (("REV", 5000000), ("NGN", 66666), ("KES", 769230)):
        for i in range(3): oracle.submit(cur, price, h, i)

    # The recipient key pays phlo for the claim; top it up if needed.
    keys = json.loads(KEYS.read_text())
    term = f'new return, vault(`rho:rchain:revVault`), ret in {{ vault!("getBalance", "{keys["sender"]["address"]}", *ret) | for (@b <- ret) {{ return!(b) }} }}'
    bal = v.ints(node.explore(term))
    if bal and bal[0] < 20_000_000:
        try: node.faucet(keys["sender"]["address"])
        except Exception as e: print("faucet:", e)
    r = run_as(v.render("account_balance_asset.rho", FACTORY_URI=factory, ASSET="NGN"))
    ngn = v.ints(r)[-1] if v.ints(r) else 0
    check("sender has NGN to send", ngn >= 100_000_000, f"ngn={ngn}")
    r = run_as(v.render("account_balance_asset.rho", FACTORY_URI=factory, ASSET="KES"))
    kes_before = v.ints(r)[-1] if v.ints(r) else 0

    secret = os.urandom(32); claim_hash = hashlib.blake2b(secret, digest_size=32).digest()
    expiry = node.height() + 100
    r = run_as(v.render("account_send_transfer.rho", FACTORY_URI=factory, SOURCE="NGN", DEST="KES",
                        AMOUNT=100_000_000, MIN_DEST=1, HASH=claim_hash.hex(), EXPIRY=expiry),
               phlo=40_000_000)
    ids = v.ints(r)
    check("send creates a transfer", v.bools(r)[:1] == [True] and len(ids) >= 1, f"ints={ids} strings={v.strings(r)}")
    transfer_id = ids[0] if ids else 0

    # Recipient (sender key) claims with the secret.
    r = run_as(v.render("account_claim_transfer.rho", FACTORY_URI=factory, ID=transfer_id,
                        DEST="KES", SECRET=secret.hex()), key="sender", phlo=10_000_000)
    check("recipient claims the transfer", v.bools(r)[:1] == [True], f"bools={v.bools(r)} strings={v.strings(r)}")
    r = run_as(v.render("account_balance_asset.rho", FACTORY_URI=factory, ASSET="KES"), key="sender")
    recv = v.ints(r)[-1] if v.ints(r) else 0
    check("recipient received KES", recv > 0, f"kes={recv}")

    # Refund: send with expiry at the current height, then refund after it passes.
    secret2 = os.urandom(32); hash2 = hashlib.blake2b(secret2, digest_size=32).digest()
    expiry2 = node.height()
    r = run_as(v.render("account_send_transfer.rho", FACTORY_URI=factory, SOURCE="NGN", DEST="KES",
                        AMOUNT=100_000_000, MIN_DEST=1, HASH=hash2.hex(), EXPIRY=expiry2),
               phlo=40_000_000)
    ids2 = v.ints(r)
    id2 = ids2[0] if ids2 else 0
    check("second transfer created", v.bools(r)[:1] == [True], f"ints={ids2}")
    # A few blocks pass before the refund (the refund itself is a later block).
    r = run_as(v.render("account_refund_transfer.rho", FACTORY_URI=factory, ID=id2, DEST="KES"),
               phlo=40_000_000)
    check("sender refunds the expired transfer", v.bools(r)[:1] == [True], f"bools={v.bools(r)} strings={v.strings(r)}")
    r = run_as(v.render("account_balance_asset.rho", FACTORY_URI=factory, ASSET="KES"))
    kes_after = v.ints(r)[-1] if v.ints(r) else 0
    check("sender received the refund in KES", kes_after > kes_before, f"before={kes_before} after={kes_after}")

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nphase 4b transfer: {passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1

if __name__ == "__main__":
    raise SystemExit(main())
