#!/usr/bin/env python3
"""Payments v0.5: memo, opId idempotency and the native REV stipend.

Funds a sender, sends a transfer with a memo, opId and stipend, then:
  - proves the recipient's native REV balance grew by the stipend;
  - replays the same opId and gets the same transfer without a second escrow;
  - proves a memo over the bound is refused and the payment returns to the purse.

Usage:
    python3 harness/unit_transfer_memo.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import deploy as node  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_v3 import call, check, faucet_top_up, one  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"
SCENARIOS = ROOT / "harness" / "scenarios"
FUND = 15_000_000
AMOUNT = 5_000_000
STIPEND = 1_000_000
SECRET = b"memo-transfer-secret"


def render(name: str, values: dict[str, str]) -> str:
    text = (SCENARIOS / f"{name}.rho").read_text()
    for key, value in values.items():
        text = text.replace(key, value)
    return minify(text)


def digest(secret: bytes) -> str:
    return hashlib.blake2b(secret, digest_size=32).hexdigest()


def native_balance(pub: str, secret: str) -> int:
    term = render("native_rev_balance", {"__PUBKEY__": pub})
    return one(term, secret)[0]


def account_balance(pub: str, root: str, secret: str) -> int:
    term = render("account_balance", {
        "__ROOT_URI__": root, "__PUBKEY__": pub, "__ASSET__": "REV",
    })
    return one(term, secret)[0][1]


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    sender = keys["key20"]
    recipient = keys["key21"]

    for name in ("key20", "key21"):
        faucet_top_up(keys[name]["address"])

    expiry = node.height() + 100
    recipient_native_before = native_balance(recipient["public"], keys["deployer"]["secret"])

    sent = one(render("transfer_send_memo", {
        "__ROOT_URI__": root,
        "__SENDER_PUB__": sender["public"],
        "__RECIPIENT_PUB__": recipient["public"],
        "__FUND__": str(FUND),
        "__AMOUNT__": str(AMOUNT),
        "__HASH__": digest(SECRET),
        "__EXPIRY__": str(expiry),
        "__MEMO__": "invoice-42",
        "__OP_ID__": "memo-op-1",
        "__STIPEND__": str(STIPEND),
    }), sender["secret"])
    sender_id, recipient_id, first_id, uri = sent
    check("sender address", sender_id, sender["address"])
    check("recipient address", recipient_id, recipient["address"])

    info = one(call(uri, "TransferContract",
                    'TransferContract!("info", *r) | for (@x <- r) { deployId!(x) }'),
               sender["secret"])[1]
    check("memo stored", info["memo"], "invoice-42")
    check("opId stored", info["opId"], "memo-op-1")
    check("stipend stored", info["stipend"], STIPEND)

    recipient_native_after = native_balance(recipient["public"], keys["deployer"]["secret"])
    check("stipend funded the claimer", recipient_native_after - recipient_native_before, STIPEND)

    balance_before = account_balance(sender["public"], root, sender["secret"])
    replay = one(render("transfer_send_only", {
        "__ROOT_URI__": root,
        "__SENDER_PUB__": sender["public"],
        "__RECIPIENT_PUB__": recipient["public"],
        "__AMOUNT__": str(AMOUNT),
        "__HASH__": digest(SECRET),
        "__EXPIRY__": str(expiry),
        "__MEMO__": "invoice-42",
        "__OP_ID__": "memo-op-1",
        "__STIPEND__": "0",
    }), sender["secret"])
    check("opId replay returns the same id", replay[1], first_id)
    check("opId replay returns the same uri", replay[2], uri)
    balance_after = account_balance(sender["public"], root, sender["secret"])
    check("opId replay moved no funds", balance_after, balance_before)

    long_memo = "x" * 129
    refused = one(render("transfer_send_only", {
        "__ROOT_URI__": root,
        "__SENDER_PUB__": sender["public"],
        "__RECIPIENT_PUB__": recipient["public"],
        "__AMOUNT__": str(AMOUNT),
        "__HASH__": digest(SECRET),
        "__EXPIRY__": str(expiry),
        "__MEMO__": long_memo,
        "__OP_ID__": "memo-op-2",
        "__STIPEND__": "0",
    }), sender["secret"])
    check("memo bound refused", refused[0], False)
    check("memo bound reason", refused[1], "memo")
    balance_after_refusal = account_balance(sender["public"], root, sender["secret"])
    check("refused payment returned to the purse", balance_after_refusal, balance_before)

    claim = one(render("transfer_claim",
                       {"__ROOT_URI__": root,
                        "__RECIPIENT_PUB__": recipient["public"],
                        "__TRANSFER_URI__": uri,
                        "__SECRET__": SECRET.hex()}),
                recipient["secret"])
    check("claim accepted", claim[0], (True, AMOUNT))

    print(f"transfer {uri} with memo and opId")
    print(f"recipient native REV {recipient_native_before} -> {recipient_native_after}")
    print("unit_transfer_memo: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
