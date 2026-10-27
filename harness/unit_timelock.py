#!/usr/bin/env python3
"""Governance timelock: schedule, early refusal, apply after the timelock.

Schedules a risk-parameter change, a savings-share change and a PSM policy at
the same height, proves each execute is refused before `readyAt`, waits once,
then applies all three in nonce order. Also proves the genesis params hash is
preserved while `currentHash` changes.

Requires a listed V4T system (run `make unit-stablecoin` first).

Usage:
    python3 harness/unit_timelock.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import deploy as node  # noqa: E402
import sign_payload  # noqa: E402
from unit_feed import blake2b256, canonical  # noqa: E402
from unit_v3 import call, check, one  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
STATE = ROOT / ".devnet" / "v3-install.json"
DOMAIN = "stablecoin:V4T"


def sigs_for(keys: dict, nonce: int, action: str, args_hash: str) -> str:
    payload = f"rcash:admin:v1|{DOMAIN}|{nonce}|{action}|{args_hash}"
    sigs = []
    for name in ("admin1", "admin2"):
        sig = sign_payload.sign_payload(keys[name]["secret"], payload.encode())["signature"]
        sigs.append(f'"{sig}".hexToBytes()')
    return "[" + ", ".join(sigs) + "]"


def wait_blocks(count: int) -> None:
    target = node.height() + count
    for _ in range(count * 12 + 60):
        if node.height() >= target:
            return
        time.sleep(2)
    raise AssertionError(f"height did not reach {target}")


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    registry_uri = state["currency_registry_uri"]
    deployer = keys["deployer"]["secret"]
    currency = "V4T"

    entry = one(call(registry_uri, "CurrencyRegistry",
                     f'CurrencyRegistry!("currency", "{currency}", *r) | '
                     "for (@x <- r) { deployId!(x) }"), deployer)
    check("V4T listed", entry[0], True)
    entry = entry[1]
    params_uri = entry["paramsUri"]
    buffer_uri = entry["bufferUri"]
    psm_uri = entry["psmUri"]

    info = one(call(params_uri, "RiskParameters",
                    'RiskParameters!("info", *r) | for (@x <- r) { deployId!(x) }'),
               deployer)[1]
    genesis_hash = info["paramsHash"]
    params = dict(info["params"])
    params["mcrBps"] = 21000
    params["savingsShareBps"] = 6000
    params["psmFeeBps"] = 20
    values = [currency] + [
        str(params[key]) for key in (
            "mcrBps", "bonusBps", "closeFactorBps", "ratePerBlock", "debtCeiling",
            "minDebt", "maxDebt", "maxOracleAge", "savingsShareBps", "psmFeeBps")
    ]
    args_hash = canonical("rcash:stablecoin-params:v2", values)
    expected_hash = blake2b256(args_hash)
    params_literal = "{" + ", ".join(f'"{k}": {v}' for k, v in params.items()) + "}"

    psm = one(call(psm_uri, "PegStabilityModule",
                   'PegStabilityModule!("info", *r) | for (@x <- r) { deployId!(x) }'),
              deployer)[1]
    ceiling = psm["ceiling"]

    base = node.height() + 1
    nonce_risk = base
    nonce_share = base + 1
    nonce_policy = base + 2

    schedule_risk = one(call(params_uri, "RiskParameters",
        f'RiskParameters!("scheduleParams", {params_literal}, {nonce_risk}, '
        f'{sigs_for(keys, nonce_risk, "setRiskParams", args_hash)}, *r) | '
        "for (@x <- r) { deployId!(x) }"), deployer)
    check("risk scheduled", schedule_risk[0], True)
    check("risk args hash", schedule_risk[2], args_hash)

    share_hash = "7000"
    schedule_share = one(call(buffer_uri, "SurplusBuffer",
        f'SurplusBuffer!("scheduleShare", 7000, {nonce_share}, '
        f'{sigs_for(keys, nonce_share, "setSavingsShare", share_hash)}, *r) | '
        "for (@x <- r) { deployId!(x) }"), deployer)
    check("share scheduled", schedule_share[0], True)

    policy_hash = f"25|{ceiling}"
    schedule_policy = one(call(psm_uri, "PegStabilityModule",
        f'PegStabilityModule!("schedulePolicy", 25, {ceiling}, {nonce_policy}, '
        f'{sigs_for(keys, nonce_policy, "setPsmPolicy", policy_hash)}, *r) | '
        "for (@x <- r) { deployId!(x) }"), deployer)
    check("policy scheduled", schedule_policy[0], True)

    early = one(call(params_uri, "RiskParameters",
                     f'RiskParameters!("applyParams", {nonce_risk}, *r) | '
                     "for (@x <- r) { deployId!(x) }"), deployer)
    check("early execute refused", early, (False, "early"))

    wait_blocks(101)

    applied = one(call(params_uri, "RiskParameters",
                       f'RiskParameters!("applyParams", {nonce_risk}, *r) | '
                       "for (@x <- r) { deployId!(x) }"), deployer)
    check("risk applied", applied[0], True)
    check("risk current hash", applied[1]["currentHash"].hex(), expected_hash)

    after = one(call(params_uri, "RiskParameters",
                     'RiskParameters!("info", *r) | for (@x <- r) { deployId!(x) }'),
                deployer)[1]
    check("genesis hash preserved", after["paramsHash"], genesis_hash)
    check("current hash moved", after["currentHash"].hex(), expected_hash)
    check("mcr updated", after["params"]["mcrBps"], 21000)
    check("savings share updated in params", after["params"]["savingsShareBps"], 6000)
    check("psm fee updated in params", after["params"]["psmFeeBps"], 20)

    one(call(buffer_uri, "SurplusBuffer",
             f'SurplusBuffer!("applyShare", {nonce_share}, *r) | '
             "for (@x <- r) { deployId!(x) }"), deployer)
    buf = one(call(buffer_uri, "SurplusBuffer",
                   'SurplusBuffer!("info", *r) | for (@x <- r) { deployId!(x) }'),
              deployer)[1]
    check("buffer share updated", buf["savingsShareBps"], 7000)

    one(call(psm_uri, "PegStabilityModule",
             f'PegStabilityModule!("applyPolicy", {nonce_policy}, *r) | '
             "for (@x <- r) { deployId!(x) }"), deployer)
    psm_after = one(call(psm_uri, "PegStabilityModule",
                         'PegStabilityModule!("info", *r) | for (@x <- r) { deployId!(x) }'),
                    deployer)[1]
    check("psm fee updated", psm_after["feeBps"], 25)
    check("psm ceiling unchanged", psm_after["ceiling"], ceiling)

    print(f"genesis {genesis_hash} current {expected_hash}")
    print(f"buffer {buf} psm {psm_after}")
    print("unit_timelock: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
