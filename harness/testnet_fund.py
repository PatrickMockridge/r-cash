#!/usr/bin/env python3
"""Fund fresh public-testnet addresses from the dev-mode faucet.

The faucet pays 0.3 REV (30,000,000 drops) per drip, at most ten drips per
address per process, and rate-limits rapid requests. This module keeps a
per-address ledger, waits for each drip to be processed and finalized, and
refuses to exceed the documented policy or the configured budget.
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
import netconfig  # noqa: E402

REV = 100_000_000
DRIP = 30_000_000
POLICY_DRIPS = 1


class AlreadyFunded(RuntimeError):
    """The node's faucet funds an address once, regardless of the doc's ten."""


class Deficit(RuntimeError):
    """The faucet cannot reach the requested target under its observed policy."""


class Blocked(RuntimeError):
    """The node is below its admission floor; no work can be submitted."""


def profile() -> dict:
    return netconfig.profile()


def load_ledger() -> dict:
    path = netconfig.FUNDING_PATH
    if path.is_file():
        return json.loads(path.read_text())
    return {"addresses": {}, "budget": {}}


def save_ledger(ledger: dict) -> None:
    path = netconfig.FUNDING_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2) + "\n")
    path.chmod(0o600)


def _post_faucet(address: str) -> dict:
    import requests
    urls = [profile()["faucetUrl"]]
    for suffix in profile().get("faucetUrlsLocal", []):
        urls.append(profile()["https"].rstrip("/") + suffix)
    last = None
    for url in dict.fromkeys(urls):
        for attempt in range(6):
            try:
                response = requests.post(url, json={"address": address},
                                         timeout=netconfig.READ_TIMEOUT)
            except requests.RequestException as error:
                last = str(error)
                time.sleep(min(2 ** attempt, 10))
                continue
            if response.status_code == 429:
                retry = response.headers.get("retry-after")
                time.sleep(int(retry) if retry and retry.isdigit() else 1.5)
                continue
            if response.status_code == 404:
                last = f"404 at {url}"
                break
            if response.status_code >= 400:
                body = response.text[:500]
                if "already funded" in body.lower():
                    raise AlreadyFunded(body)
                last = f"{response.status_code}: {body}"
                break
            return response.json()
    raise RuntimeError(f"faucet refused {address}: {last}")


def _status(deploy_id: str) -> tuple[str, dict]:
    for _ in range(int(netconfig.DEPLOY_TIMEOUT / 2)):
        try:
            doc = node.deploy_status(deploy_id)
        except node.Refusal:
            time.sleep(1)
            continue
        variant, payload = node._variant(doc)
        if variant in ("processedwithsuccess", "processedwitherror"):
            return variant, payload
        time.sleep(2)
    raise RuntimeError(f"faucet deploy {deploy_id} not processed")


def drip(address: str, ledger: dict | None = None) -> int:
    """Request one drip, wait for finality, and update the ledger."""
    ledger = ledger if ledger is not None else load_ledger()
    entry = ledger["addresses"].setdefault(
        address, {"drips": 0, "credited": 0, "deploys": []})
    if entry["drips"] >= POLICY_DRIPS:
        raise Deficit(f"{address}: faucet policy exhausted ({POLICY_DRIPS} drips)")
    try:
        response = _post_faucet(address)
    except AlreadyFunded:
        current = balance(address)
        entry["drips"] += 1
        entry["credited"] = max(entry["credited"], current)
        ledger["budget"]["credited"] = max(ledger["budget"].get("credited", 0), current)
        save_ledger(ledger)
        if current <= 0:
            raise Deficit(f"{address}: faucet says funded but balance is {current}")
        return 0
    deploy_id = response.get("deployId") or response.get("deploy_id")
    amount = int(response.get("amount") or DRIP)
    if response.get("deployError"):
        raise RuntimeError(f"{address}: faucet error {response['deployError']}")
    if not deploy_id:
        raise RuntimeError(f"{address}: faucet returned no deployId: {response}")
    entry["drips"] += 1
    entry["deploys"].append(deploy_id)
    save_ledger(ledger)
    variant, payload = _status(deploy_id)
    if variant == "processedwitherror":
        raise RuntimeError(f"{address}: faucet deploy failed: {payload.get('deployError')}")
    block = (payload.get("block") or {}).get("blockHash")
    if block and not node.wait_finalized(block, timeout=netconfig.FINALITY_TIMEOUT):
        raise RuntimeError(f"{address}: faucet block {block} did not finalise")
    entry["credited"] += amount
    ledger["budget"]["credited"] = ledger["budget"].get("credited", 0) + amount
    save_ledger(ledger)
    return amount


def balance(address: str) -> int:
    """Native REV balance via a read-only exploratory deploy."""
    term = (
        "new return, revVault(`rho:rchain:revVault`), ret in { "
        f'revVault!("getBalance", "{address}", *ret) | '
        "for (@b <- ret) { return!(b) } }"
    )
    doc = node.explore(term)
    value = _find_int(doc)
    return int(value or 0)


def _find_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        for key in ("ExprInt", "exprInt"):
            if key in value:
                data = value[key]
                if isinstance(data, dict):
                    return int(data.get("data", 0))
                return int(data)
        for child in value.values():
            found = _find_int(child)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _find_int(child)
            if found is not None:
                return found
    return None


def ensure(address: str, target: int, ledger: dict | None = None) -> int:
    """Fund one address to at most one drip.

    The live faucet refuses a second drip to an address, so a target above
    30,000,000 drops cannot be met here. Callers that need more use bank
    addresses and `consolidate`; that is a computed deficit, not a retry.
    """
    if target > DRIP:
        raise Deficit(
            f"{address}: target {target} exceeds one drip ({DRIP}); "
            "fund bank addresses and consolidate")
    ledger = ledger if ledger is not None else load_ledger()
    current = balance(address)
    if current >= target:
        return current
    drip(address, ledger)
    current = balance(address)
    if current < target:
        raise Deficit(f"{address}: balance {current} < target {target} after one drip")
    return current


def transfer(source: dict, target: dict, amount: int) -> dict:
    """Move native REV from the source key to the target REV address."""
    if amount <= 0:
        raise RuntimeError("transfer amount must be positive")
    term = (
        "new revAddress(`rho:rev:address`), revVault(`rho:rchain:revVault`), "
        "deployerId(`rho:rchain:deployerId`), deployId(`rho:rchain:deployId`), "
        "aCh, vCh in { "
        f'revAddress!("fromPublicKey", "{target["public"]}".hexToBytes(), *aCh) | '
        "for (@addr <- aCh) { "
        f'revVault!("transfer", *deployerId, addr, {amount}, *vCh) | '
        "for (@ok <- vCh) { deployId!(ok) } } }"
    )
    deploy_id = node.deploy(term, source["secret"], phlo_limit=2_000_000)
    return {"deployId": deploy_id, "result": node.deploy_result(deploy_id)}


def consolidate(keys: dict, ledger: dict, assignments: dict[str, str]) -> None:
    """Transfer each bank's spendable REV to the named target key."""
    reserve = 2_000_000  # leave enough for the transfer's own precharge
    for bank_name, target_name in assignments.items():
        source = keys[bank_name]
        target = keys[target_name]
        current = balance(source["address"])
        amount = max(0, current - reserve)
        if amount <= 0:
            print(f"{bank_name}: no spendable balance")
            continue
        before = balance(target["address"])
        try:
            receipt = transfer(source, target, amount)
        except (node.Refusal, node.DevnetError) as error:
            if "503" in str(error) or "throttled" in str(error).lower():
                raise Blocked(f"consolidation stopped at {bank_name}: {error}") from error
            raise
        after = balance(target["address"])
        if after < before + amount:
            raise RuntimeError(
                f"{bank_name}->{target_name}: credited {after - before} of {amount}")
        ledger.setdefault("consolidation", []).append({
            "from": bank_name, "to": target_name, "amount": amount,
            "deployId": receipt["deployId"],
        })
        save_ledger(ledger)
        print(f"{bank_name}->{target_name}: {amount / REV:.3f} REV")


def admission() -> None:
    """Refuse to start funding when the node already rejects all work."""
    status = node._json("GET", "/api/v1/status")
    degraded = status.get("degraded")
    if not status.get("acceptsDeploys") or degraded not in (None, "normal"):
        raise Blocked(
            f"node degraded={degraded} acceptsDeploys={status.get('acceptsDeploys')} "
            f"height={status.get('latestBlockNumber')}: deploy and explore work refused")


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=DRIP,
                    help="drops per ordinary key (default one drip)")
    ap.add_argument("--deployer-target", type=int, default=3 * REV)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--plan", action="store_true",
                    help="print the address/drip/consolidation plan and exit")
    args = ap.parse_args(argv)
    if not netconfig.is_testnet():
        raise SystemExit("testnet funding requires RCASH_NET=testnet")
    keys = netconfig.load_keys()
    ledger = load_ledger()
    roles = [name for name in keys if not name.startswith("bank")]
    deploy_banks = [f"bank{i}" for i in range(1, 26)]
    market_banks = [f"bank{i}" for i in range(26, 74)]
    banks = [name for name in deploy_banks + market_banks if name in keys]
    if args.plan:
        gross = (len(roles) + len(banks)) * DRIP
        spendable = max(0, len(banks) * (DRIP - 2_000_000))
        print(json.dumps({
            "role_addresses": len(roles), "banks": len(banks),
            "deployer_banks": len(deploy_banks), "key18_banks": len(market_banks),
            "faucet_requests": len(roles) + len(banks),
            "gross_rev": gross / REV,
            "bank_spendable_rev": spendable / REV,
            "deployer_target_rev": 7.0, "key18_target_rev": 13.0,
            "note": "live faucet funds one drip per address; banks are consolidated",
        }, indent=2))
        return 0
    try:
        admission()
    except Blocked as error:
        print(f"BLOCKED platform: {error}", file=sys.stderr)
        return 3
    targets = {name: DRIP for name in roles + banks}
    for name in roles + banks:
        entry = keys[name]
        address = entry["address"]
        target = targets[name]
        current = ledger["addresses"].get(address, {}).get("credited", 0)
        if not args.force and current >= target:
            print(f"{name}: ledger says {current} >= {target}, skip")
            continue
        try:
            got = ensure(address, target, ledger)
            print(f"{name}: {address} {got / REV:.3f} REV")
        except RuntimeError as error:
            print(f"{name}: FAILED {error}", file=sys.stderr)
            save_ledger(ledger)
            return 1
    assignments = {}
    for name in deploy_banks:
        assignments[name] = "deployer"
    for name in market_banks:
        assignments[name] = "key18"
    if any(name in keys for name in assignments):
        try:
            consolidate(keys, ledger, {k: v for k, v in assignments.items() if k in keys})
        except Blocked as error:
            save_ledger(ledger)
            print(f"BLOCKED platform: {error}", file=sys.stderr)
            return 3
        except RuntimeError as error:
            print(f"consolidation FAILED {error}", file=sys.stderr)
            save_ledger(ledger)
            return 1
    save_ledger(ledger)
    checks = {"deployer": 7 * REV, "key18": 13 * REV}
    failed = False
    for name, need in checks.items():
        have = balance(keys[name]["address"])
        print(f"{name}: {have / REV:.3f} REV (need {need / REV:.3f})")
        if have < need:
            print(f"DEFICIT key={name} have={have} need={need} "
                  f"deficit={need - have}", file=sys.stderr)
            failed = True
    print(json.dumps({"credited": ledger["budget"].get("credited", 0) / REV},
                     indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
