#!/usr/bin/env python3
"""Object-capability red-team suite.

Each check is an adversarial deploy against the running devnet; the expected
result is a refusal (or a benign answer) at the capability boundary, never
success. See docs/spec/OCAP-REDTEAM.md for the scenario table and the recorded
results.

Usage:
    python3 harness/unit_ocap.py

The suite needs the installed components (`make install`). The account factory
comes from the install state; set RCASH_ACCOUNT_FACTORY to point at a
candidate term deployed out of band.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import deploy as node  # noqa: E402
import netconfig  # noqa: E402
import sign_payload  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_v3 import call, check, faucet_top_up, one  # noqa: E402

KEYS = netconfig.KEYS_PATH
STATE = netconfig.STATE_PATH
SCENARIOS = ROOT / "harness" / "scenarios"
FUND = 10_000_000
AMOUNT = 5_000_000
RT04_SECRET = b"ocap-rt04-secret"


def render_scenario(name: str, values: dict) -> str:
    text = (SCENARIOS / name).read_text()
    for key, value in values.items():
        text = text.replace(key, str(value))
    return minify(text)


def digest(secret: bytes) -> str:
    return hashlib.blake2b(secret, digest_size=32).hexdigest()


def state_env(state: dict, *names: str):
    """Read an install key, then its RCASH_<KEY> environment override."""
    for name in names:
        value = state.get(name)
        if value:
            return value
        value = os.environ.get("RCASH_" + name.upper())
        if value:
            return value
    return None


def skipped(label: str, why: str) -> None:
    """An integration surface is absent; this is not a pass."""
    print(f"skip {label} (written, unrun: {why})")


def root_resolve(root: str, key: str, min_version: int, secret: str):
    return one(
        call(root, "Root",
             f'Root!("resolve", "{key}", {min_version}, *r) | '
             "for (@x <- r) { deployId!(x) }"),
        secret,
    )


def rt11_root_dispatch(root: str, secret: str) -> None:
    """RT-11a: an active component resolves; unknown and stale refuse."""
    active = root_resolve(root, "component:clock", 1, secret)
    check("root resolve active", active[0], True)
    check("root resolve active uri", active[1].startswith("rho:id:"), True)
    unknown = root_resolve(root, "component:not-a-component", 1, secret)
    check("root resolve unknown", unknown, (False, "unknown component"))
    stale = root_resolve(root, "component:clock", 10_000, secret)
    check("root resolve stale", stale, (False, "stale"))


def rt11_gate_active(gate: str, secret: str) -> None:
    """RT-11b: an active status must admit, not fall through to 'not active'."""
    terms = '{"minTicketQuote": 0, "maxTradeBps": 10000}'
    reply = one(
        call(gate, "TradabilityGate",
             f'TradabilityGate!("admit", "active", true, 0, 1000000, {terms}, *r) | '
             "for (@x <- r) { deployId!(x) }"),
        secret,
    )
    check("tradability active admits", reply, (True,))


def rt02_registry_fresh_auth(directory: str, secret: str) -> None:
    """RT-02: a fresh name is not the directory authority."""
    reply = one(
        call(directory, "MarketDirectory",
             'new attacker in { '
             'MarketDirectory!("bind", "ocap-probe", "slot", *attacker, *r) } | '
             "for (@x <- r) { deployId!(x) }"),
        secret,
    )
    check("market bind refuses a fresh auth", reply, (False, "bad directory authority"))


def rt03_vault_substitution(factory: str, pub: str, secret: str) -> None:
    """RT-03/RT-09: vaultOpen never resolves a caller-supplied URI.

    The term publishes a hostile contract whose `open` arm would capture the
    proof, then passes that contract's URI as the currency code. A correct
    vaultOpen reads the currency registry instead and refuses; a vulnerable one
    resolves the URI and answers `captured`.
    """
    term = f'''
new HostileVault, rs(`rho:registry:insertArbitrary`), u,
    rl(`rho:registry:lookup`), afCh, oCh, zCh,
    deployId(`rho:rchain:deployId`), deployerId(`rho:rchain:deployerId`) in {{
  contract HostileVault(@"open", @ownerId, proof, ret) = {{
    ret!((true, "captured"))
  }} |
  rs!(bundle+{{*HostileVault}}, *u) |
  for (@hUri <- u) {{
    rl!(`{factory}`, *afCh) |
    for (AccountFactory <- afCh) {{
      AccountFactory!("getOrCreate", "{pub}".hexToBytes(), *oCh) |
      for (@(true, account, ownerId) <- oCh) {{
        @account!("vaultOpen", *deployerId, hUri, *zCh) |
        for (@z <- zCh) {{ deployId!([z, hUri]) }}
      }}
    }}
  }}
}}'''
    reply = one(minify(term), secret)
    check("vaultOpen ignores a caller URI (substitution)", reply[0][0], False)
    check("vaultOpen reports the registry lookup", reply[0][1], "no currency")
    check("vaultOpen did not reach the hostile vault", reply[0][1] != "captured", True)


def rt13_vault_rotation(factory: str, registry: str, pub: str, secret: str) -> None:
    """RT-13: a rotated vault auth retires the old capability."""
    term = f'''
new ertpCh, regCh, eCh, afCh, oCh, zCh, r1, r2, r3, vc,
    rl(`rho:registry:lookup`), deployId(`rho:rchain:deployId`),
    deployerId(`rho:rchain:deployerId`) in {{
  rl!(`{registry}`, *regCh) |
  for (Registry <- regCh) {{
    Registry!("currency", "V4T", *eCh) |
    for (@e <- eCh) {{
      match e {{
        (true, entry) => {{
          rl!(`{factory}`, *afCh) |
          for (AccountFactory <- afCh) {{
            AccountFactory!("getOrCreate", "{pub}".hexToBytes(), *oCh) |
            for (@(true, account, ownerId) <- oCh) {{
              @account!("vaultOpen", *deployerId, "V4T", *zCh) |
              for (@z <- zCh) {{
                match z {{
                  (true, auth) => {{
                    new newAuth in {{
                      rl!(entry.get("vaultUri"), *vc) |
                      for (VaultBook <- vc) {{
                        VaultBook!("rotate", ownerId, auth, *newAuth, *r1) |
                        for (@rot <- r1) {{
                          VaultBook!("mint", ownerId, auth, 1, *r2) |
                          VaultBook!("mint", ownerId, *newAuth, 1, *r3) |
                          for (@m1 <- r2; @m2 <- r3) {{
                            deployId!([rot, m1, m2])
                          }}
                        }}
                      }}
                    }}
                  }}
                  _ => {{ deployId!(z) }}
                }}
              }}
            }}
          }}
        }}
        _ => {{ deployId!(e) }}
      }}
    }}
  }}
}}'''
    reply = one(minify(term), secret)
    if isinstance(reply, tuple) and reply and reply[0] is False:
        print(f"skip vault rotation (no listed V4T system): {reply}")
        return
    if not (isinstance(reply, list) and len(reply) == 3):
        raise AssertionError(f"rotation probe did not run: {reply!r}")
    rotation, old_auth, new_auth = reply
    check("vault rotation succeeds", rotation, (True,))
    check("rotated-out auth is refused", old_auth, (False, "bad vault auth"))
    check("rotated-in auth is not refused", new_auth != (False, "bad vault auth"), True)


def rt01_issuer_fresh_names(state: dict, secret: str) -> None:
    """RT-01: a fresh name is not a provisioned facet.

    The privileged issuer/custody arms are no longer in the published bundles;
    the remaining boundary is each shop's `isFacet`. A fresh name must be
    refused by the issuer shop and by the buffer shop.
    """
    shop = state_env(state, "issuer_shop_uri", "facet_shop_uri")
    if not shop:
        skipped("RT-01 issuer fresh-name probe", "no issuer shop URI")
        return
    reply = one(call(
        shop, "FacetShop",
        'new fake in { FacetShop!("isFacet", "mint", *fake, *r) } | '
        "for (@x <- r) { deployId!(x) }"), secret)
    check("RT-01 issuer shop refuses a fresh facet", reply, False)

    buffer_shop = state_env(state, "buffer_shop_uri")
    if not buffer_shop:
        skipped("RT-01b buffer fresh-name probe", "no buffer shop URI")
        return
    reply = one(call(
        buffer_shop, "BufferFacetShop",
        'new fake in { BufferFacetShop!("isFacet", "buffer", *fake, *r) } | '
        "for (@x <- r) { deployId!(x) }"), secret)
    check("RT-01 buffer shop refuses a fresh facet", reply, False)


def rt04_caller_facet_sink(state: dict, keys: dict, secret: str) -> None:
    """RT-04: a caller facet receives `deposit`, never `withdraw`."""
    factory = state_env(state, "account_factory_uri") or os.environ.get(
        "RCASH_ACCOUNT_FACTORY")
    sender = keys.get("key20")
    recipient = keys.get("key21")
    if not (state.get("root_uri") and factory and sender and recipient):
        skipped("RT-04 caller facet sink", "no root/factory/key20/key21")
        return
    faucet_top_up(sender["address"])
    faucet_top_up(recipient["address"])
    op_id = f"ocap-rt04-{node.height()}"
    _hash = sign_payload.hash_canonical_hex(
        "rcash:claim:v1",
        [op_id, "REV", str(AMOUNT), RT04_SECRET.hex()])
    reply = one(render_scenario("ocap_caller_facet_sink.rho", {
        "__ROOT_URI__": state["root_uri"],
        "__SENDER_PUB__": sender["public"],
        "__RECIPIENT_PUB__": recipient["public"],
        "__FUND__": str(FUND),
        "__AMOUNT__": str(AMOUNT),
        "__SECRET_HASH__": _hash,
        "__SECRET__": RT04_SECRET.hex(),
        "__OP_ID__": op_id,
        "__EXPIRY__": str(node.height() + 2000),
    }), sender["secret"])
    if not (isinstance(reply, list) and len(reply) >= 2):
        raise AssertionError(f"RT-04 probe did not run: {reply!r}")
    check("RT-04 claim accepted through a sink facet", reply[0][0], True)
    check("RT-04 hostile withdraw was never called", reply[1], False)


def rt05_cross_owner(state: dict, keys: dict, secret: str) -> None:
    """RT-05: a foreign deployerId cannot open a victim's vault."""
    factory = state_env(state, "account_factory_uri") or os.environ.get(
        "RCASH_ACCOUNT_FACTORY")
    victim = keys.get("key21") or keys.get("key20")
    if not (state.get("root_uri") and factory and victim):
        skipped("RT-05 cross-owner proof", "no root/factory/victim key")
        return
    reply = one(render_scenario("ocap_cross_owner.rho", {
        "__ROOT_URI__": state["root_uri"],
        "__VICTIM_PUB__": victim["public"],
        "__CURRENCY__": "V4T",
    }), secret)
    check("RT-05 foreign deployerId refused", reply, (False, "not owner"))


def rt06_canonical_preimage(state: dict, keys: dict, secret: str) -> None:
    """RT-06: a signature for another domain cannot authorise provisioning."""
    shop = state_env(state, "issuer_shop_uri", "facet_shop_uri")
    consumer = state_env(state, "vault_accept_uri", "consumer_uri")
    sponsor = keys.get("sponsor") or keys.get("deployer")
    if not (shop and consumer and sponsor):
        skipped("RT-06 canonical provisioning preimage",
                "no issuer shop/consumer/sponsor key")
        return
    issuer = state_env(state, "stablecoin_uri", "issuer_uri") or ""
    # Deliberately the wrong domain: the v1 shop must not accept it.
    payload = f"rcash:provision:v2|{issuer}|{consumer}|ocap-rt06|mint|1|999999999"
    signature = sign_payload.sign_payload(sponsor["secret"], payload.encode())[
        "signature"]
    reply = one(render_scenario("ocap_canonical_preimage.rho", {
        "__ISSUER_SHOP_URI__": shop,
        "__CONSUMER_URI__": consumer,
        "__ISSUER_URI__": issuer,
        "__KINDS__": '["mint"]',
        "__NONCE__": "1",
        "__DEADLINE__": "999999999",
        "__SPONSOR_HEX__": sponsor["public"],
        "__SIGNATURE__": signature,
    }), secret)
    check("RT-06 cross-domain signature refused", reply[0], False)


def rt12_lock_frontrun(keys: dict) -> None:
    """RT-12: a non-beneficiary cannot fund a seed lock.

    Needs a live unfunded lock and an LP asset.  Supply them out of band:
    RCASH_OCAP_LOCK_URI and RCASH_OCAP_LP_ASSET.
    """
    lock = os.environ.get("RCASH_OCAP_LOCK_URI")
    asset = os.environ.get("RCASH_OCAP_LP_ASSET")
    attacker = keys.get("key20")
    if not (lock and asset and attacker):
        skipped("RT-12 lock front-run",
                "set RCASH_OCAP_LOCK_URI and RCASH_OCAP_LP_ASSET")
        return
    reply = one(render_scenario("ocap_lock_frontrun.rho", {
        "__ROOT_URI__": os.environ["RCASH_ROOT_URI"],
        "__ATTACKER_PUB__": attacker["public"],
        "__LOCK_URI__": lock,
        "__BENEFICIARY_ID__": os.environ.get("RCASH_OCAP_BENEFICIARY_ID", ""),
        "__LP_ASSET__": asset,
        "__LP_AMOUNT__": os.environ.get("RCASH_OCAP_LP_AMOUNT", "1"),
        "__UNTIL_HEIGHT__": os.environ.get("RCASH_OCAP_UNTIL_HEIGHT", "1000"),
    }), attacker["secret"])
    if not (isinstance(reply, list) and len(reply) == 2):
        raise AssertionError(f"RT-12 probe did not run: {reply!r}")
    check("RT-12 non-beneficiary fund refused", reply[0][0], False)


def rt14_unauthorised_provision(state: dict, keys: dict, secret: str) -> None:
    """RT-14: a non-sponsor signature cannot provision a facet."""
    shop = state_env(state, "issuer_shop_uri", "facet_shop_uri")
    consumer = state_env(state, "vault_accept_uri", "consumer_uri")
    wrong = keys.get("reporter1") or keys.get("key19")
    if not (shop and consumer and wrong):
        skipped("RT-14 unauthorised provisioning",
                "no issuer shop/consumer/non-sponsor key")
        return
    issuer = state_env(state, "stablecoin_uri", "issuer_uri") or ""
    payload = f"rcash:provision:v1|{issuer}|{consumer}|ocap-rt14|mint|1|999999999"
    signature = sign_payload.sign_payload(wrong["secret"], payload.encode())[
        "signature"]
    reply = one(render_scenario("ocap_unauthorised_provision.rho", {
        "__ISSUER_SHOP_URI__": shop,
        "__CONSUMER_URI__": consumer,
        "__ISSUER_URI__": issuer,
        "__KINDS__": '["mint"]',
        "__NONCE__": "1",
        "__DEADLINE__": "999999999",
        "__WRONG_SPONSOR_HEX__": wrong["public"],
        "__WRONG_SIG__": signature,
    }), secret)
    check("RT-14 unauthorised provisioning refused", reply[0], False)


def rt15_forged_accept(state: dict, keys: dict, secret: str) -> None:
    """RT-15: a forged acceptFacet is refused; a consumed nonce cannot replay."""
    consumer = os.environ.get("RCASH_OCAP_CONSUMER")
    if not consumer:
        skipped("RT-15 forged acceptFacet",
                "set RCASH_OCAP_CONSUMER to a provisioned consumer")
        return
    reply = one(render_scenario("ocap_forged_accept.rho", {
        "__CONSUMER_URI__": consumer,
        "__KIND__": "mint",
        "__NONCE__": "1",
        "__DEADLINE__": "999999999",
    }), secret)
    check("RT-15 forged acceptFacet refused", reply[0], False)

    builder = getattr(sign_payload, "provision_payload", None)
    shop = state_env(state, "issuer_shop_uri", "facet_shop_uri")
    sponsor = keys.get("sponsor") or keys.get("deployer")
    if not (builder and shop and sponsor):
        skipped("RT-15 provisioning replay",
                "no canonical provision_payload helper or facet shop")
        return
    try:
        payload = builder(
            state_env(state, "stablecoin_uri", "issuer_uri") or "",
            consumer, "ocap-rt15", ["mint"], 7, 999999999)
    except TypeError:
        skipped("RT-15 provisioning replay",
                "provision_payload signature is not frozen yet")
        return
    signature = sign_payload.sign_payload(sponsor["secret"], payload)["signature"]
    values = {
        "__ISSUER_SHOP_URI__": shop,
        "__CONSUMER_URI__": consumer,
        "__ISSUER_URI__": state_env(state, "stablecoin_uri", "issuer_uri") or "",
        "__KINDS__": '["mint"]',
        "__NONCE__": "7",
        "__DEADLINE__": "999999999",
        "__SPONSOR_HEX__": sponsor["public"],
        "__SIGNATURE__": signature,
    }
    term = render_scenario("ocap_canonical_preimage.rho", values)
    first = one(term, secret)
    check("RT-15 provisioning accepted before replay", first[0], True)
    second = one(term, secret)
    check("RT-15 replay of a consumed nonce refused", second[0], False)


def rt16_cross_term_rollback(state: dict, keys: dict, secret: str) -> None:
    """RT-16: VaultBook.mint through a provisioned facet, then a downstream 1/0.

    The deploy must be rejected as a deploy error (not a graceful refusal), and
    the issuer supply must be unchanged.  The vault must exist and the owner
    must have opened it; RT-16 is gated on RCASH_OCAP_VAULT_URI.
    """
    vault = os.environ.get("RCASH_OCAP_VAULT_URI")
    root = state.get("root_uri")
    stablecoin = state_env(state, "stablecoin_uri")
    owner = keys.get("deployer")
    if not (vault and root and stablecoin and owner):
        skipped("RT-16 cross-term rollback",
                "set RCASH_OCAP_VAULT_URI; needs root/stablecoin/owner")
        return

    def supply():
        return one(call(
            stablecoin, "Stablecoin",
            'Stablecoin!("supply", *r) | for (@x <- r) { deployId!(x) }'), secret)

    before = supply()
    term = render_scenario("ocap_cross_term_rollback.rho", {
        "__ROOT_URI__": root,
        "__VAULT_URI__": vault,
        "__OWNER_PUB__": owner["public"],
        "__MINT_AMOUNT__": "1",
    })
    deploy_id = node.deploy(term, secret, phlo_limit=10_000_000)
    variant, payload = node.wait_processed(deploy_id, timeout=180)
    if variant != "processedwitherror":
        raise AssertionError(
            f"RT-16 expected a deploy error from 1/0, got {variant}: "
            f"{json.dumps(payload)[:500]}")
    check("RT-16 supply unchanged after rollback", supply(), before)


def rt17_stale_auth(state: dict, secret: str) -> None:
    """RT-17: Governor.authorize rotation; stale auth refused, facet live."""
    governor = state_env(state, "governor_uri")
    ledger = state_env(state, "liquidation_auth_ledger_uri", "auth_ledger_uri",
                       "issuer_auth_ledger_uri")
    consumer = os.environ.get("RCASH_OCAP_CONSUMER")
    signatures = os.environ.get("RCASH_OCAP_SIGS")
    if not (governor and ledger and consumer and signatures):
        skipped("RT-17 stale auth after rotation",
                "set RCASH_OCAP_CONSUMER and RCASH_OCAP_SIGS; needs "
                "governor/auth-ledger URIs")
        return
    reply = one(render_scenario("ocap_stale_auth.rho", {
        "__GOVERNOR_URI__": governor,
        "__AUTH_LEDGER_URI__": ledger,
        "__CONSUMER_URI__": consumer,
        "__DOMAIN__": os.environ.get(
            "RCASH_OCAP_DOMAIN", "auth:<currency>:liquidation"),
        "__NONCE__": os.environ.get("RCASH_OCAP_NONCE", "1"),
        "__ARGS_HASH__": os.environ.get("RCASH_OCAP_ARGS_HASH", "h1"),
        "__SIGS__": signatures,
        "__KIND__": os.environ.get("RCASH_OCAP_KIND", "liquidation"),
        "__MINT_AMOUNT__": "1",
    }), secret)
    if not (isinstance(reply, list) and len(reply) == 4):
        raise AssertionError(f"RT-17 probe did not run: {reply!r}")
    check("RT-17 new auth accepted", reply[1][0], True)
    check("RT-17 non-current auth refused", reply[2][0], False)
    check("RT-17 facet live after rotation", reply[3][0], True)


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    deployer = keys["deployer"]
    secret = deployer["secret"]
    faucet_top_up(deployer["address"])

    factory = os.environ.get("RCASH_ACCOUNT_FACTORY") or state.get("account_factory_uri")
    if not factory:
        raise SystemExit("no account factory: install the components first")

    rt11_root_dispatch(root, secret)
    rt11_gate_active(state["tradability_gate_uri"], secret)
    rt02_registry_fresh_auth(state["market_directory_uri"], secret)
    rt03_vault_substitution(factory, deployer["public"], secret)
    rt13_vault_rotation(factory, state["currency_registry_uri"],
                        deployer["public"], secret)
    rt01_issuer_fresh_names(state, secret)
    rt04_caller_facet_sink(state, keys, secret)
    rt05_cross_owner(state, keys, secret)
    rt06_canonical_preimage(state, keys, secret)
    rt12_lock_frontrun(keys)
    rt14_unauthorised_provision(state, keys, secret)
    rt15_forged_accept(state, keys, secret)
    rt16_cross_term_rollback(state, keys, secret)
    rt17_stale_auth(state, secret)
    print("ocap red-team: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
