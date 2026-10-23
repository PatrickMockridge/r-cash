#!/usr/bin/env python3
"""Install the v0.2 core on the running devnet.

This first stage deploys Directory, OracleHubV2, ListingRegistry, AccountFactoryV2
and the component registration. Zones/feeds/markets are added in later stages.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import deploy as node  # noqa: E402
import market_terms  # noqa: E402
import sign_payload  # noqa: E402
from minify_rho import minify  # noqa: E402

KEYS = ROOT / ".devnet" / "keys.json"
BUILT = ROOT / "contracts" / "build" / "deploy" / "v2"
STATE = ROOT / ".devnet" / "v2-install.json"
MANIFEST = ROOT / "deployments" / "devnet-v2.json"
PHLO = 100_000_000
NODE_COMMIT = "e2d073dcd02f1e560ccb84749937138a1e184b0b"

ZONE_VALUES = [20000, 800, 5000, 3171, 10_000_000_000_000, 1_000_000, 10_000_000_000_000]
ZONE_KEYS = ["__ZONE_MCR__", "__ZONE_BONUS__", "__ZONE_CLOSE__", "__ZONE_RATE__",
             "__ZONE_CEILING__", "__ZONE_MIN_DEBT__", "__ZONE_MAX_DEBT__"]
FEED_VALUES = [2, 50, 200, 1, 1_000_000_000_000, 10, 4]
LIVE_CURRENCIES = ("NGN", "KES")
FEED_CURRENCIES = ("REV", "NGN", "KES")
FEED_PRICES = {"REV": 5_000_000, "NGN": 66_666, "KES": 769_230}


def key_list(keys: dict, names: list[str]) -> str:
    return "[" + ", ".join(f'"{keys[n]["public"]}".hexToBytes()' for n in names) + "]"


def walk(value, out: list[str]) -> list[str]:
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("ExprUri", "ExprString") and isinstance(v, dict):
                out.append(v.get("data"))
            else:
                walk(v, out)
    elif isinstance(value, list):
        for v in value:
            walk(v, out)
    return out


def render(name: str, replacements: dict[str, str]) -> str:
    path = BUILT / f"{name}.rho"
    term = path.read_text()
    for key, value in replacements.items():
        term = term.replace(key, value)
    unresolved = sorted(set(__import__("re").findall(r"__[A-Z0-9_]+__", term)))
    if unresolved:
        raise SystemExit(f"{name}: unresolved placeholders {unresolved}")
    term = minify(term)
    size = len(term.encode())
    if size > 65_536:
        raise SystemExit(f"{name}: term is {size} bytes, over the 64 KiB limit")
    print(f"{name}: {size} bytes")
    return term


def deploy_step(name: str, replacements: dict[str, str]) -> dict:
    keys = json.loads(KEYS.read_text())
    term = render(name, replacements)
    deploy_id = node.deploy(term, keys["deployer"]["secret"], phlo_limit=PHLO)
    print(f"{name}: deploy {deploy_id}")
    variant, payload = node.wait_processed(deploy_id, timeout=300)
    if variant != "processedwithsuccess":
        raise SystemExit(f"{name}: {variant} {json.dumps(payload)[:3000]}")
    uris = [
        uri
        for uri in walk(payload.get("deployResult"), [])
        if isinstance(uri, str) and uri.startswith("rho:id:")
    ]
    block = payload.get("block") or {}
    return {
        "deploy_id": deploy_id,
        "uris": uris,
        "block_hash": block.get("blockHash"),
        "block_number": block.get("blockNumber"),
    }


def save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    admins = key_list(keys, ["admin1", "admin2", "admin3"])
    reporters = key_list(keys, ["reporter1", "reporter2", "reporter3"])

    if "directory_uri" not in state:
        step = deploy_step("00_directory", {})
        if len(step["uris"]) != 2:
            raise SystemExit(f"00_directory: expected 2 URIs, got {step['uris']}")
        state.update(
            directory_uri=step["uris"][0],
            components_uri=step["uris"][1],
            directory_deploy=step["deploy_id"],
        )
        save(state)
        print(state)

    if "oracle_uri" not in state:
        step = deploy_step(
            "01_oracle",
            {
                "__REPORTER_KEYS__": reporters,
                "__ADMIN_KEYS__": admins,
                "__ORACLE_PARAMS__": "{}",
            },
        )
        if len(step["uris"]) != 1:
            raise SystemExit(f"01_oracle: expected 1 URI, got {step['uris']}")
        state.update(oracle_uri=step["uris"][0], oracle_deploy=step["deploy_id"])
        save(state)
        print(state)

    if "registry_deploy" not in state:
        step = deploy_step(
            "02_registry",
            {
                "__ORACLE_URI__": state["oracle_uri"],
                "__COMPONENTS_URI__": state["components_uri"],
                "__ADMIN_KEYS__": admins,
                "__PINNED_CURRENCIES__": "{ \"NGN\": \"%s\", \"KES\": \"%s\" }"
                % (keys["sponsor"]["public"], keys["sponsor"]["public"]),
            },
        )
        # The registry is a live capability in ComponentRegistry, not a URI.
        state.update(
            registry_uri=state["components_uri"],
            registry_key="component:listings",
            registry_deploy=step["deploy_id"],
        )
        save(state)
        print(state)

    if "accounts_uri" not in state:
        step = deploy_step(
            "03_accounts",
            {
                "__DIRECTORY_URI__": state["directory_uri"],
                "__COMPONENTS_URI__": state["components_uri"],
            },
        )
        if len(step["uris"]) != 1:
            raise SystemExit(f"03_accounts: expected 1 URI, got {step['uris']}")
        state.update(accounts_uri=step["uris"][0], accounts_deploy=step["deploy_id"])
        save(state)
        print(state)

    if "components_deploy" not in state:
        # Directory registration is not used by v0.2 capability resolution (ComponentRegistry
        # is), and this devnet currently wedges when 04 is proposed. Keep it opt-in.
        if os.environ.get("RCASH_REGISTER_DIRECTORY") == "1":
            step = deploy_step(
                "04_register",
                {
                    "__DIRECTORY_URI__": state["directory_uri"],
                    "__ACCOUNTS_URI__": state["accounts_uri"],
                    "__ORACLE_URI__": state["oracle_uri"],
                },
            )
            state.update(components_deploy=step["deploy_id"])
        else:
            state.update(components_deploy="skipped")
        save(state)
        print(state)

    zones = state.setdefault("zones", {})
    currencies = state.setdefault("currencies", {})
    zone_hash = market_terms.digest(
        market_terms.canonical(market_terms.ZONE_SCHEMA, ZONE_VALUES)
    )
    sponsor = keys["sponsor"]

    for code in LIVE_CURRENCIES:
        if code not in zones:
            replacements = {
                "__CURRENCY__": code,
                "__ADMIN_KEYS__": admins,
                "__ORACLE_URI__": state["oracle_uri"],
                "__ACCOUNTS_URI__": state["accounts_uri"],
            }
            replacements.update({k: str(v) for k, v in zip(ZONE_KEYS, ZONE_VALUES)})
            step = deploy_step("05_zone", replacements)
            if len(step["uris"]) != 1:
                raise SystemExit(f"05_zone {code}: expected 1 URI, got {step['uris']}")
            zones[code] = step["uris"][0]
            save(state)
            print(f"zone {code}: {zones[code]}")

        if code not in currencies:
            zone_uri = zones[code]
            payload = (
                f"rcash:listing-currency:v1|/root|{code}|{zone_uri}|"
                f"{zone_hash}|{sponsor['public']}"
            ).encode()
            sig = sign_payload.sign_payload(sponsor["secret"], payload)["signature"]
            step = deploy_step(
                "30_register_currency",
                {
                    "__COMPONENTS_URI__": state["components_uri"],
                    "__CODE__": code,
                    "__ZONE_URI__": zone_uri,
                    "__PARAMS_HASH__": zone_hash,
                    "__SPONSOR_PUB__": sponsor["public"],
                    "__SPONSOR_SIG__": sig,
                },
            )
            currencies[code] = {
                "zone_uri": zone_uri,
                "params_hash": zone_hash,
                "register_deploy": step["deploy_id"],
            }
            save(state)
            print(f"currency {code}: registered")

    feeds = state.setdefault("feeds", {})
    feed_hash = market_terms.digest(
        market_terms.canonical(market_terms.FEED_SCHEMA, FEED_VALUES)
    )
    reporters = [keys[f"reporter{i}"] for i in (1, 2, 3)]

    def noop() -> int:
        deploy_id = node.deploy("Nil", keys["deployer"]["secret"], phlo_limit=2_000_000)
        node.wait_processed(deploy_id, timeout=180)
        return node.height()

    def submit(code: str, price: int, index: int) -> None:
        reporter = reporters[index]
        height = node.height()
        payload = sign_payload.oracle_payload(code, price, height)
        sig = sign_payload.sign_payload(reporter["secret"], payload)["signature"]
        deploy_step(
            "32_feed_submit",
            {
                "__ORACLE_URI__": state["oracle_uri"],
                "__CODE__": code,
                "__PRICE__": str(price),
                "__HEIGHT__": str(height),
                "__INDEX__": str(index),
                "__PUBKEY__": reporter["public"],
                "__SIG__": sig,
            },
        )

    for code in FEED_CURRENCIES:
        if code not in feeds:
            k0, k1, k2 = (r["public"] for r in reporters)
            payload = (
                f"rcash:oracle-feed:v1|/root|{code}|{k0}|{k1}|{k2}|"
                f"{sponsor['public']}|2|50|200|1|1000000000000|10|4"
            ).encode()
            sig = sign_payload.sign_payload(sponsor["secret"], payload)["signature"]
            step = deploy_step(
                "31_open_feed",
                {
                    "__ORACLE_URI__": state["oracle_uri"],
                    "__CODE__": code,
                    "__K0__": k0,
                    "__K1__": k1,
                    "__K2__": k2,
                    "__SPONSOR_PUB__": sponsor["public"],
                    "__SIG__": sig,
                },
            )
            feeds[code] = {
                "opened_at": step["block_number"],
                "policy_hash": feed_hash,
                "open_deploy": step["deploy_id"],
            }
            save(state)
            print(f"feed {code}: opened at {step['block_number']}")

        if not feeds[code].get("active"):
            for _ in range(2):
                submit(code, FEED_PRICES[code], 0)
                submit(code, FEED_PRICES[code], 1)
            while node.height() < feeds[code]["opened_at"] + 10:
                noop()
            step = deploy_step(
                "33_feed_activate",
                {"__ORACLE_URI__": state["oracle_uri"], "__CODE__": code},
            )
            feeds[code]["active"] = True
            feeds[code]["activate_deploy"] = step["deploy_id"]
            save(state)
            print(f"feed {code}: activated")

    markets = state.setdefault("markets", {})
    market_id = "KES/NGN:v1"
    if os.environ.get("RCASH_REDEPLOY_MARKET") == "1":
        markets.pop(market_id, None)
    if market_id not in markets:
        base, quote, version = "NGN", "KES", 1
        sponsor = keys["sponsor"]
        base_zone = zones[base]
        quote_zone = zones[quote]
        feed_hash = feeds[base]["policy_hash"]
        now = node.height()
        terms = {
            "marketId": market_id,
            "slug": "KES-NGN-v1",
            "base": base,
            "quote": quote,
            "version": version,
            "sponsorPubKey": sponsor["public"],
            "sponsorOwnerId": sponsor["address"],
            "baseZoneUri": base_zone,
            "quoteZoneUri": quote_zone,
            "baseFeedPolicyHash": feed_hash,
            "quoteFeedPolicyHash": feeds[quote]["policy_hash"],
            "baseSpreadBps": 20,
            "skewSpreadBps": 80,
            "maxTradeBps": 500,
            "minLiquidity": 100_000_000,
            "firstDepositToleranceBps": 100,
            "depthFloorUsdE8": 100_000_000,
            "depthFloorQuote": 130_000_000_000,
            "minTicketUsdE8": 1_000_000,
            "minTicketQuote": 1_300_000_000,
            "seedBase": 1_500_000_000_000,
            "seedQuote": 130_000_000_000,
            "seedInitialShares": 2_000_000_000,
            "lockBeneficiaryPubKey": sponsor["public"],
            "lockMinBlocks": 10,
            "lockUntilHeight": now + 60,
            "bookDefaultExpiryBlocks": 720,
            "bookMaxExpiryBlocks": 129_600,
            "protocolFeeBps": 0,
            "autoPause": 1,
            "lpAssetId": f"LP:{base}/{quote}:v{version}",
        }
        values = [
            market_id, "KES-NGN-v1", base, quote, str(version), sponsor["public"],
            sponsor["address"], base_zone, quote_zone, feed_hash,
            feeds[quote]["policy_hash"], "20", "80", "500", "100000000", "100",
            "100000000", "130000000000", "1000000", "1300000000",
            "1500000000000", "130000000000", "2000000000", sponsor["public"],
            "10", str(now + 60), "720", "129600", "0", "1",
        ]
        terms_hash = market_terms.digest(
            market_terms.canonical(market_terms.TERMS_SCHEMA, values)
        )
        sponsor_payload = (
            f"rcash:listing-sponsor:v1|{market_id}|{sponsor['public']}|{terms_hash}"
        ).encode()
        sponsor_sig = sign_payload.sign_payload(
            sponsor["secret"], sponsor_payload
        )["signature"]
        market_replace = {
            "__BASE__": base,
            "__QUOTE__": quote,
            "__MARKET_ID__": market_id,
            "__TERMS_HASH__": terms_hash,
            "__COMPONENTS_URI__": state["components_uri"],
            "__ADMIN_KEYS__": admins,
        }
        pool_params = (
            '{ "baseSpreadBps": 20, "skewSpreadBps": 80, "maxTradeBps": 500, '
            '"minLiquidity": 100000000, "firstDepositToleranceBps": 100, '
            '"depthFloorQuote": 130000000000, "minTicketQuote": 1300000000 }'
        )
        book_params = '{ "defaultExpiryBlocks": 720, "maxExpiryBlocks": 129600 }'
        deploy_step("20_pool", {
            **market_replace,
            "__ORACLE_URI__": state["oracle_uri"],
            "__BASE_ZONE_URI__": base_zone,
            "__QUOTE_ZONE_URI__": quote_zone,
            "__POOL_PARAMS__": pool_params,
        })
        deploy_step("21_lock", {
            **market_replace,
            "__SPONSOR_PUB__": sponsor["public"],
            "__SPONSOR_OWNER__": sponsor["address"],
            "__INITIAL_SHARES__": "2000000000",
            "__LOCK_UNTIL__": str(now + 60),
        })
        deploy_step("22_book", {
            **market_replace,
            "__ACCOUNTS_URI__": state["accounts_uri"],
            "__BASE_ZONE_URI__": base_zone,
            "__QUOTE_ZONE_URI__": quote_zone,
            "__BOOK_PARAMS__": book_params,
        })
        rho_terms = "{ " + ", ".join(
            f'"{k}": ' + (f'"{v}"' if isinstance(v, str) else str(v))
            for k, v in terms.items()
        ) + " }"
        rho_values = "[" + ", ".join(
            f'"{v}"' if isinstance(v, (str,)) else str(v) for v in values
        ) + "]"
        step = deploy_step("23_stage", {
            **market_replace,
            "__VERSION__": str(version),
            "__STAGE_NONCE__": str(now),
            "__TERMS_MAP__": rho_terms,
            "__TERMS_VALUES__": rho_values,
            "__SPONSOR_SIG__": sponsor_sig,
        })
        markets[market_id] = {
            "slug": "KES-NGN-v1",
            "base": base,
            "quote": quote,
            "status": "draft",
            "terms_hash": terms_hash,
            "stage_deploy": step["deploy_id"],
            "stage_nonce": now,
        }
        save(state)
        print(f"market {market_id}: staged")

    state.setdefault("node_commit", NODE_COMMIT)
    state.setdefault("generated", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    MANIFEST.write_text(json.dumps(state, indent=2) + "\n")
    print(f"wrote {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
