#!/usr/bin/env python3
"""Exercise v0.4 send, claim and refund.

The sender funds its account, creates two REV transfers and escrows them in
per-transfer cells. The recipient claims the first; the second is exercised
through the wrong-secret, foreign-refund, expired-refund and closed-claim paths.

Run after `make install-v3`; the TransferBook is installed with the kernel.

Usage:
    python3 harness/unit_transfer.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import netconfig  # noqa: E402

import deploy as node  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_v3 import check, faucet_top_up, one  # noqa: E402

KEYS = netconfig.KEYS_PATH
STATE = netconfig.STATE_PATH
SCENARIOS = ROOT / "harness" / "scenarios"
FUND = 10_000_000
AMOUNT = 5_000_000
SECRET_A = b"transfer-secret-A"
SECRET_B = b"transfer-secret-B"
WRONG_SECRET = b"not-the-secret"


def render_scenario(name: str, values: dict) -> str:
    text = (SCENARIOS / name).read_text()
    for key, value in values.items():
        text = text.replace(key, value)
    return minify(text)


def digest(secret: bytes) -> str:
    return hashlib.blake2b(secret, digest_size=32).hexdigest()


def wait_height(target: int) -> None:
    import time, urllib.request
    deadline = time.time() + 900
    while time.time() < deadline:
        if node.height() > target:
            return
        try:
            urllib.request.urlopen(urllib.request.Request(
                "http://localhost:40405/api/v1/propose", data=b"{}",
                headers={"content-type": "application/json"}, method="POST"), timeout=5)
        except Exception:
            pass
        time.sleep(0.2)
    raise AssertionError(f"height did not pass {target}")


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    sender = keys["key20"]
    recipient = keys["key21"]
    foreign = keys["key19"]
    for key in (sender, recipient, foreign):
        faucet_top_up(key["address"])

    height = node.height()
    expiry_a = height + 100
    expiry_b = height + 100
    send_term = render_scenario("transfer_send.rho", {
        "__ROOT_URI__": root,
        "__SENDER_PUB__": sender["public"],
        "__RECIPIENT_PUB__": recipient["public"],
        "__FUND__": str(FUND),
        "__AMOUNT__": str(AMOUNT),
        "__HASH_A__": digest(SECRET_A),
        "__EXPIRY_A__": str(expiry_a),
        "__HASH_B__": digest(SECRET_B),
        "__EXPIRY_B__": str(expiry_b),
    })
    sent = one(send_term, sender["secret"])
    sender_id, recipient_id, id_a, uri_a, id_b, uri_b = sent
    check("sender address", sender_id, sender["address"])
    check("recipient address", recipient_id, recipient["address"])
    check("transfer ids allocated", [id_a, id_b], [0, 1])
    print(f"transfer A: {uri_a}")
    print(f"transfer B: {uri_b}")

    claim_term = render_scenario("transfer_claim.rho", {
        "__ROOT_URI__": root,
        "__RECIPIENT_PUB__": recipient["public"],
        "__TRANSFER_URI__": uri_a,
        "__SECRET__": SECRET_A.hex(),
    })
    claimed, recipient_balance = one(claim_term, recipient["secret"])
    check("claim accepted", claimed, (True, AMOUNT))
    check("recipient credited", recipient_balance, (True, AMOUNT))

    # Before expiry the wrong secret is refused and a foreign refund is refused as
    # "not expired"; the expiry gate runs before the secret and the sender check.
    early_refuse = render_scenario("transfer_refuse.rho", {
        "__ROOT_URI__": root,
        "__OWN_PUB__": foreign["public"],
        "__TRANSFER_URI__": uri_b,
        "__WRONG_SECRET__": WRONG_SECRET.hex(),
    })
    wrong_secret, foreign_early = one(early_refuse, foreign["secret"])
    check("wrong secret refused", wrong_secret, (False, "bad secret"))
    check("foreign refund before expiry", foreign_early, (False, "not expired"))

    wait_height(expiry_b)

    refuse_term = render_scenario("transfer_refuse.rho", {
        "__ROOT_URI__": root,
        "__OWN_PUB__": foreign["public"],
        "__TRANSFER_URI__": uri_b,
        "__WRONG_SECRET__": WRONG_SECRET.hex(),
    })
    expired_claim, foreign_refund = one(refuse_term, foreign["secret"])
    check("claim after expiry", expired_claim, (False, "expired"))
    check("foreign refund refused", foreign_refund, (False, "not sender"))

    refund_term = render_scenario("transfer_refund.rho", {
        "__ROOT_URI__": root,
        "__SENDER_PUB__": sender["public"],
        "__TRANSFER_URI__": uri_b,
    })
    refunded, sender_balance = one(refund_term, sender["secret"])
    check("refund after expiry", refunded, (True, AMOUNT))
    check("sender credited", sender_balance, (True, AMOUNT))

    closed_claim, _ = one(render_scenario("transfer_claim.rho", {
        "__ROOT_URI__": root,
        "__RECIPIENT_PUB__": recipient["public"],
        "__TRANSFER_URI__": uri_b,
        "__SECRET__": SECRET_B.hex(),
    }), recipient["secret"])
    check("claim after refund closed", closed_claim, (False, "closed"))

    closed_refund, _ = one(render_scenario("transfer_refund.rho", {
        "__ROOT_URI__": root,
        "__SENDER_PUB__": sender["public"],
        "__TRANSFER_URI__": uri_a,
    }), sender["secret"])
    check("refund after claim closed", closed_refund, (False, "closed"))

    print(json.dumps({"sender": sender_id, "recipient": recipient_id,
                      "transfers": [{"id": id_a, "uri": uri_a, "state": "claimed"},
                                    {"id": id_b, "uri": uri_b, "state": "refunded"}]},
                     indent=2))
    print("unit_transfer: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
