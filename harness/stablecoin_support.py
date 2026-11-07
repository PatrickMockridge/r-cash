#!/usr/bin/env python3
"""Render, deploy and provision the multi-term stablecoin system.

This module owns the hybrid deploy used while T2/T3/T4 are still absent: it
deploys T5 (risk parameters), T1 (issuer core) and the transitional monolith
(VaultBook, PSM, buffer and savings), then provisions T1's four issuer facets
into the monolith consumer and registers the eight component URIs.

The privileged ABI is the one in docs/spec/MULTI-TERM.md section 3 (revised):
`BurnFacet!("burn", payment, @maxAmount, ret)`,
`SettlementFacet!("settle", payment, @principal, @interest, ret)`,
`CustodyFacet!("deposit", payment, ret)` and `CustodyFacet!("withdraw", @amount, ret)`.
`MintFacet!("mint", @amount, ret)` is unchanged.

Extension points for the sibling terms are at the bottom of this file. They are
deliberately explicit: a consumer provisioned for T2 carries five kinds, four
from the issuer shop and one from the buffer shop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import netconfig  # noqa: E402

import deploy as node  # noqa: E402
import sign_payload  # noqa: E402
from install_v3 import render  # noqa: E402
from unit_v3 import call, faucet_top_up, one  # noqa: E402

KEYS = netconfig.KEYS_PATH
STATE = netconfig.STATE_PATH
PHLO = 100_000_000

# The protocol constant shared by T1's issuer state and the transitional PSM.
MAX_SUPPLY = 2_000_000_000_000_000
PARAMS_SCHEMA = "rcash:stablecoin-params:v2"
PROVISION_SCHEMA = sign_payload.PROVISION_SCHEMA
LISTING_SCHEMA = "rcash:currency-register:v4"

# T2 receives four issuer facets and one buffer facet. The issuer shop serves
# the first four; T3's BufferFacetShop serves the fifth.
ISSUER_KINDS = ("mint", "burn", "settle", "custody")
BUFFER_KINDS = ("buffer",)
T2_KINDS = ISSUER_KINDS + BUFFER_KINDS
T4_KINDS = ("mint", "burn")
T3_KINDS = ("burn",)


# ---------------------------------------------------------------------------
# Parameters


DEFAULT_PARAMS = {
    "mcrBps": 20000,
    "bonusBps": 800,
    "closeFactorBps": 5000,
    "ratePerBlock": 3171,
    "debtCeiling": 10000000000000,
    "minDebt": 1000000,
    "maxDebt": 10000000000000,
    "maxOracleAge": 50,
    "savingsShareBps": 5000,
    "psmFeeBps": 10,
}

PARAM_FIELDS = (
    "mcrBps", "bonusBps", "closeFactorBps", "ratePerBlock", "debtCeiling",
    "minDebt", "maxDebt", "maxOracleAge", "savingsShareBps", "psmFeeBps",
)


def params_for(currency: str, config: dict | None = None) -> tuple[dict, list[str], str]:
    """Return (params map, canonical values, params hash) for one currency."""
    if config:
        p = config["issuerDefaults"]
    else:
        p = DEFAULT_PARAMS
    params = {field: p[field] for field in PARAM_FIELDS}
    values = [currency] + [str(params[field]) for field in PARAM_FIELDS]
    params_hash = sign_payload.hash_canonical_hex(PARAMS_SCHEMA, values)
    return params, values, params_hash


# ---------------------------------------------------------------------------
# Renderers (pure; the caller chooses the deploy path)


def render_params_term(currency: str, params: dict, params_hash: str,
                       sponsor: str, root: str) -> str:
    return render("31_params", {
        "__ROOT_URI__": root,
        "__CURRENCY__": currency,
        "__PARAMS__": json.dumps(params),
        "__PARAMS_HASH__": params_hash,
        "__SPONSOR_PUB__": sponsor,
    })


def render_issuer(currency: str, params_hash: str, sponsor: str, root: str) -> str:
    return render("31_issuer", {
        "__ROOT_URI__": root,
        "__CURRENCY__": currency,
        "__PARAMS_HASH__": params_hash,
        "__SPONSOR_PUB__": sponsor,
    })


def render_legacy(currency: str, root: str, issuer_uri: str, params_uri: str,
                  issuer_shop_uri: str, buffer_shop_uri: str = "") -> str:
    """Retired transitional monolith; kept only for older branches."""
    return render("31_stablecoin", {
        "__ROOT_URI__": root,
        "__CURRENCY__": currency,
        "__ISSUER_URI__": issuer_uri,
        "__PARAMS_URI__": params_uri,
        "__ISSUER_SHOP_URI__": issuer_shop_uri,
        "__BUFFER_SHOP_URI__": buffer_shop_uri,
    })


def render_buffer_savings(currency: str, params: dict, params_hash: str,
                          sponsor: str, root: str, sc_uri: str,
                          issuer_shop_uri: str) -> str:
    return render("31_buffer_savings", {
        "__ROOT_URI__": root,
        "__STABLECOIN_URI__": sc_uri,
        "__FACET_SHOP_URI__": issuer_shop_uri,
        "__CURRENCY__": currency,
        "__PARAMS_HASH__": params_hash,
        "__SPONSOR_PUB__": sponsor,
        "__SAVINGS_SHARE_BPS__": str(params["savingsShareBps"]),
    })


def render_psm(currency: str, params: dict, params_hash: str, sponsor: str,
               root: str, sc_uri: str, issuer_shop_uri: str) -> str:
    return render("31_psm", {
        "__ROOT_URI__": root,
        "__STABLECOIN_URI__": sc_uri,
        "__FACET_SHOP_URI__": issuer_shop_uri,
        "__CURRENCY__": currency,
        "__PARAMS_HASH__": params_hash,
        "__SPONSOR_PUB__": sponsor,
        "__PSM_FEE_BPS__": str(params["psmFeeBps"]),
        "__PSM_CEILING__": str(params["debtCeiling"]),
        "__MAX_SUPPLY__": str(2_000_000_000_000_000),
        "__MAX_ORACLE_AGE__": str(params["maxOracleAge"]),
    })


def render_vault(currency: str, params_hash: str, sponsor: str, root: str,
                 sc_uri: str, params_uri: str, buffer_uri: str, psm_uri: str,
                 issuer_shop_uri: str, buffer_shop_uri: str) -> str:
    return render("31_vault", {
        "__ROOT_URI__": root,
        "__CURRENCY__": currency,
        "__PARAMS_URI__": params_uri,
        "__PARAMS_HASH__": params_hash,
        "__SPONSOR_PUB__": sponsor,
        "__SC_URI__": sc_uri,
        "__BUFFER_URI__": buffer_uri,
        "__PSM_URI__": psm_uri,
        "__ISSUER_SHOP_URI__": issuer_shop_uri,
        "__BUFFER_SHOP_URI__": buffer_shop_uri,
    })


DEFAULT_RENDERERS = {
    "vault": render_vault,
    "buffer_savings": render_buffer_savings,
    "psm": render_psm,
}


# ---------------------------------------------------------------------------
# Provisioning and listing payloads


def provision_values(issuer_uri: str, consumer_uri: str, consumer_tag: str,
                     kinds: tuple[str, ...] | list[str], nonce: int,
                     deadline: int, sponsor: str) -> list[str]:
    """Canonical rcash:provision:v1 values, in contract order."""
    return [issuer_uri, consumer_uri, consumer_tag, ",".join(kinds),
            str(nonce), str(deadline), sponsor]


def provision_signature(secret: str, issuer_uri: str, consumer_uri: str,
                        consumer_tag: str, kinds, nonce: int, deadline: int,
                        sponsor: str) -> str:
    values = provision_values(issuer_uri, consumer_uri, consumer_tag, kinds,
                              nonce, deadline, sponsor)
    payload = sign_payload.canonical(PROVISION_SCHEMA, values).encode()
    return sign_payload.sign_payload(secret, payload)["signature"]


def provision_groups(kinds, issuer_shop_uri: str,
                     buffer_shop_uri: str = "") -> dict[str, list[str]]:
    """Route each kind to the shop that owns it.

    T1's issuer shop serves mint/burn/settle/custody; T3's `BufferFacetShop`
    serves buffer. A consumer maps kind to shop and verifies the received facet
    with that shop's `isFacet`.
    """
    groups: dict[str, list[str]] = {}
    for kind in kinds:
        if kind in BUFFER_KINDS:
            if not buffer_shop_uri:
                raise ValueError("buffer kind requires a buffer shop URI")
            shop = buffer_shop_uri
        else:
            shop = issuer_shop_uri
        groups.setdefault(shop, []).append(kind)
    return groups


def provision_term(shop_uri: str, consumer_uri: str, consumer_tag: str,
                   kinds, nonce: int, deadline: int, sponsor: str,
                   signature: str) -> str:
    kinds_literal = "[" + ", ".join(json.dumps(k) for k in kinds) + "]"
    return (
        "new rl(`rho:registry:lookup`), ch, r, "
        "deployId(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{shop_uri}`, *ch) |\n"
        "  for (Shop <- ch) {\n"
        f'    Shop!("provision", "{consumer_uri}", "{consumer_tag}", {kinds_literal}, '
        f'{nonce}, {deadline}, "{sponsor}", "{signature}".hexToBytes(), *r) |\n'
        "    for (@x <- r) {\n"
        "      match x {\n"
        '        (true, "provisioned") => deployId!([true, "provisioned"])\n'
        "        _ => deployId!(x)\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}"
    )


def listing_values(currency: str, sc_uri: str, custody_uri: str, params_uri: str,
                   vault_uri: str, liq_uri: str, savings_uri: str, psm_uri: str,
                   buffer_uri: str, params_hash: str, sponsor: str) -> list[str]:
    return [currency, sc_uri, custody_uri, params_uri, vault_uri, liq_uri,
            savings_uri, psm_uri, buffer_uri, params_hash, sponsor]


def listing_signature(secret: str, *values: str) -> str:
    payload = sign_payload.canonical(LISTING_SCHEMA, list(values)).encode()
    return sign_payload.sign_payload(secret, payload)["signature"]


def register_term(registry_uri: str, currency: str, sc_uri: str, custody_uri: str,
                  params_uri: str, vault_uri: str, liq_uri: str, savings_uri: str,
                  psm_uri: str, buffer_uri: str, params_hash: str, sponsor: str,
                  signature: str) -> str:
    """Registry body; expects `deployerId`, `deployId` and `r` in scope."""
    return (
        f'CurrencyRegistry!("register", "{currency}", "{sc_uri}", "{custody_uri}", '
        f'"{params_uri}", "{vault_uri}", "{liq_uri}", "{savings_uri}", "{psm_uri}", '
        f'"{buffer_uri}", "{params_hash}", "{sponsor}", '
        f'"{signature}".hexToBytes(), *deployerId, *r) |\n'
        "  for (@x <- r) {\n"
        "    match x {\n"
        "      (true, entry) => deployId!([true, entry])\n"
        '      (false, why) => deployId!([false, why])\n'
        "      _ => deployId!(x)\n"
        "    }\n"
        "  }"
    )


def full_register_term(registry_uri: str, *args, signature: str) -> str:
    """Complete deploy term for the v4 register arm (OCAP-11 deployer id)."""
    body = register_term(registry_uri, *args, signature=signature)
    return (
        "new rl(`rho:registry:lookup`), ch, r, "
        "deployerId(`rho:rchain:deployerId`), "
        "deployId(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{registry_uri}`, *ch) |\n"
        "  for (Registry <- ch) {\n"
        f"    {body}\n"
        "  }\n"
        "}"
    )


# ---------------------------------------------------------------------------
# Devnet deploy path


def deploy_term(term: str, secret: str) -> list:
    deploy_id = node.deploy(term, secret, phlo_limit=PHLO)
    variant, payload = node.wait_processed(deploy_id, timeout=300)
    if variant != "processedwithsuccess":
        raise AssertionError(f"term deploy {variant}: {json.dumps(payload)[:3000]}")
    block = payload.get("block") or {}
    if block.get("blockHash"):
        node.wait_finalized(block["blockHash"])
    result = node.deploy_result(deploy_id, timeout=300)
    from unit_v3 import decode
    decoded = decode(result)
    if not decoded:
        raise AssertionError("deploy returned no result")
    return decoded[0]


def render_params(currency: str, params: dict, params_hash: str, sponsor: str,
                  root: str) -> str:
    return render_params_term(currency, params, params_hash, sponsor, root)


def build_provision_term(calls: list[tuple], consumer_uri: str,
                         consumer_tag: str, sponsor: str) -> str:
    """One deploy that calls each shop's `provision` in sequence.

    `calls` is [(shop_uri, kinds, nonce, deadline, signature)]. A consumer that
    receives five T2 kinds therefore needs one deploy: four kinds from T1's
    issuer shop and the buffer kind from T3's `BufferFacetShop`.
    """
    next_term = 'deployId!([true, "provisioned"])'
    for index in reversed(range(len(calls))):
        shop_uri, kinds, nonce, deadline, signature = calls[index]
        kinds_literal = "[" + ", ".join(json.dumps(k) for k in kinds) + "]"
        ch = f"ch{index}"
        reply = f"r{index}"
        shop = f"Shop{index}"
        inner = (
            f'new {ch}, {reply} in {{'
            f" rl!(`{shop_uri}`, *{ch}) |"
            f" for ({shop} <- {ch}) {{"
            f' {shop}!("provision", "{consumer_uri}", "{consumer_tag}", '
            f'{kinds_literal}, {nonce}, {deadline}, "{sponsor}", '
            f'"{signature}".hexToBytes(), *{reply}) |'
            f" for (@x{index} <- {reply}) {{"
            f" match x{index} {{"
            f" (true, _) => {{ {next_term} }}"
            f" _ => deployId!(x{index})"
            f" }} }} }} }}"
        )
        next_term = inner
    return next_term


def provision_facets(keys: dict, state: dict, consumer: str, consumer_uri: str,
                     kinds, *, issuer_shop_uri: str | None = None,
                     buffer_shop_uri: str | None = None,
                     sponsor_key: str = "sponsor", nonce: int | None = None,
                     deadline: int | None = None,
                     secret: str | None = None) -> dict[str, bool]:
    """Provision `kinds` into `consumer_uri` in one deploy.

    Kinds are routed by shop: mint/burn/settle/custody to `issuer_shop_uri`,
    buffer to `buffer_shop_uri`. Both calls happen in the same deploy, so T2's
    five kinds still cost one provisioning deploy. Returns {kind: bool}.
    """
    issuer_shop_uri = issuer_shop_uri or state.get("issuer_shop_uri")
    if buffer_shop_uri is None:
        buffer_shop_uri = state.get("buffer_shop_uri", "")
    if not issuer_shop_uri:
        raise ValueError("no issuer shop URI in state")
    secret = secret or keys["deployer"]["secret"]
    sponsor = keys[sponsor_key]["public"]
    groups = provision_groups(kinds, issuer_shop_uri, buffer_shop_uri)
    base_nonce = node.height() if nonce is None else nonce
    if deadline is None:
        deadline = base_nonce + 40
    calls = []
    for index, (shop_uri, group) in enumerate(sorted(groups.items())):
        group_nonce = base_nonce + index
        group_deadline = deadline + index
        signature = provision_signature(
            keys[sponsor_key]["secret"], shop_uri, consumer_uri, consumer,
            group, group_nonce, group_deadline, sponsor)
        calls.append((shop_uri, group, group_nonce, group_deadline, signature))
    result = one(build_provision_term(calls, consumer_uri, consumer, sponsor),
                 secret)
    ok = bool(result and result[0] is True)
    return {kind: ok for kind in kinds}


def deploy_currency_system(keys: dict, state: dict, currency: str,
                           params: dict | None = None,
                           params_hash: str | None = None,
                           sponsor_sig: str | None = None,
                           config: dict | None = None,
                           sponsor_key: str = "sponsor",
                           kinds=None, nonce: int | None = None,
                           deadline: int | None = None,
                           buffer_shop_uri: str = "",
                           consumer_uri: str | None = None,
                           consumer_tag: str = "vault",
                           renderers: dict | None = None,
                           secret: str | None = None) -> dict:
    """Compatibility entry point used by the sibling harnesses.

    Deploys T5 and T1, then either the transitional monolith or the injected
    T2/T3/T4 renderers, provisions the consumer and returns the eight component
    URIs plus `vault_consumer_uri`. `sponsor_sig` is accepted for the retired
    create envelope; the live trust anchor is the signed eight-URI listing.
    """
    root = state["root_uri"]
    sponsor = keys[sponsor_key]["public"]
    secret = secret or keys["deployer"]["secret"]
    if params is None or params_hash is None:
        params, _values, params_hash = params_for(currency, config)

    params_result = deploy_term(
        render_params(currency, params, params_hash, sponsor, root), secret)
    params_uri, params_attest = params_result[0], params_result[1]

    issuer_result = deploy_term(
        render_issuer(currency, params_hash, sponsor, root), secret)
    (sc_uri, custody_uri, auth_ledger_uri, issuer_shop_uri,
     issuer_attest) = issuer_result

    renderers = DEFAULT_RENDERERS if renderers is None else renderers
    if renderers:
        # T3 publishes the buffer shop T2 needs, T4 is independent of T2 at
        # deploy (it resolves the registry per arm), and T2 pins both.
        deployed_bs = deploy_term(renderers["buffer_savings"](
            root=root, currency=currency, params=params,
            params_hash=params_hash, sponsor=sponsor, sc_uri=sc_uri,
            issuer_shop_uri=issuer_shop_uri), secret)
        savings_uri, buffer_uri, buffer_shop_uri = (
            deployed_bs[0], deployed_bs[1], deployed_bs[2])
        deployed_psm = deploy_term(renderers["psm"](
            root=root, currency=currency, params=params,
            params_hash=params_hash, sponsor=sponsor, sc_uri=sc_uri,
            issuer_shop_uri=issuer_shop_uri), secret)
        psm_uri = deployed_psm[0]
        deployed_vault = deploy_term(renderers["vault"](
            root=root, currency=currency, params_hash=params_hash,
            sponsor=sponsor, sc_uri=sc_uri, params_uri=params_uri,
            buffer_uri=buffer_uri, psm_uri=psm_uri,
            issuer_shop_uri=issuer_shop_uri,
            buffer_shop_uri=buffer_shop_uri), secret)
        vault_uri, liq_uri, vault_consumer_uri = (
            deployed_vault[0], deployed_vault[1], deployed_vault[2])
        liquidation_auth_ledger_uri = (
            deployed_vault[3] if len(deployed_vault) > 3 else None)
    else:
        legacy_result = deploy_term(
            render_legacy(currency, root, sc_uri, params_uri, issuer_shop_uri,
                          buffer_shop_uri), secret)
        (vault_consumer_uri, vault_uri, liq_uri, savings_uri, buffer_uri,
         psm_uri) = legacy_result
        # The transitional monolith has no separate liquidation ledger.
        liquidation_auth_ledger_uri = None

    provision_consumer = consumer_uri or vault_consumer_uri
    provision_kinds = tuple(kinds) if kinds is not None else T2_KINDS
    base_nonce = nonce if nonce is not None else node.height()
    # T3 consumes the issuer burn facet; T4 the issuer mint/burn; T2 all four
    # issuer facets plus the buffer facet from T3's shop. Distinct issuer-shop
    # nonces keep the one-shot ledger honest across the three deploys.
    provisioned_t3 = provision_facets(
        keys, state, "buffer", buffer_uri, T3_KINDS,
        issuer_shop_uri=issuer_shop_uri, buffer_shop_uri=buffer_shop_uri,
        sponsor_key=sponsor_key, nonce=base_nonce, deadline=deadline,
        secret=secret)
    provisioned_t4 = provision_facets(
        keys, state, "psm", psm_uri, T4_KINDS,
        issuer_shop_uri=issuer_shop_uri, buffer_shop_uri=buffer_shop_uri,
        sponsor_key=sponsor_key, nonce=base_nonce + 1, deadline=deadline,
        secret=secret)
    provisioned = provision_facets(
        keys, state, consumer_tag, provision_consumer, provision_kinds,
        issuer_shop_uri=issuer_shop_uri, buffer_shop_uri=buffer_shop_uri,
        sponsor_key=sponsor_key, nonce=base_nonce + 2, deadline=deadline,
        secret=secret)
    state["issuer_shop_uri"] = issuer_shop_uri
    state["buffer_shop_uri"] = buffer_shop_uri
    state.update({
        "stablecoin_uri": sc_uri,
        "custody_uri": custody_uri,
        "params_uri": params_uri,
        "vault_uri": vault_uri,
        "liquidation_uri": liq_uri,
        "savings_uri": savings_uri,
        "psm_uri": psm_uri,
        "buffer_uri": buffer_uri,
        "surplus_buffer_uri": buffer_uri,
        "vault_accept_uri": vault_consumer_uri,
        "issuer_auth_ledger_uri": auth_ledger_uri,
        "liquidation_auth_ledger_uri": liquidation_auth_ledger_uri,
    })
    try:
        STATE.write_text(json.dumps(state, indent=2) + "\n")
    except OSError:
        pass

    return {
        "currency": currency,
        "params": params,
        "params_hash": params_hash,
        "sponsor_sig": sponsor_sig,
        "params_uri": params_uri,
        "params_attest": params_attest,
        "sc_uri": sc_uri,
        "stablecoin_uri": sc_uri,
        "custody_uri": custody_uri,
        "auth_ledger_uri": auth_ledger_uri,
        "issuer_shop_uri": issuer_shop_uri,
        "buffer_shop_uri": buffer_shop_uri,
        "issuer_attest": issuer_attest,
        "consumer_uri": provision_consumer,
        "vault_consumer_uri": provision_consumer,
        "vault_uri": vault_uri,
        "liquidation_auth_ledger_uri": liquidation_auth_ledger_uri,
        "liq_uri": liq_uri,
        "liquidation_uri": liq_uri,
        "savings_uri": savings_uri,
        "buffer_uri": buffer_uri,
        "psm_uri": psm_uri,
        "provisioned": provisioned,
        "provisioned_t3": provisioned_t3,
        "provisioned_t4": provisioned_t4,
    }


def deploy_system(keys: dict, state: dict, currency: str,
                  config: dict | None = None, sponsor_key: str = "sponsor",
                  kinds=None, nonce: int | None = None,
                  deadline: int | None = None, buffer_shop_uri: str = "",
                  consumer_uri: str | None = None,
                  consumer_tag: str = "vault",
                  renderers: dict | None = None,
                  register: bool = True) -> dict:
    """Deploy and (by default) register the whole system."""
    system = deploy_currency_system(
        keys, state, currency, config=config, sponsor_key=sponsor_key,
        kinds=kinds, nonce=nonce, deadline=deadline,
        buffer_shop_uri=buffer_shop_uri, consumer_uri=consumer_uri,
        consumer_tag=consumer_tag, renderers=renderers)
    if not register:
        return system

    registry_uri = state["currency_registry_uri"]
    sponsor = keys[sponsor_key]["public"]
    # OCAP-11: the registry derives the deployer key and requires it to equal
    # the sponsor. Fund it, then submit the signed listing from that key.
    faucet_top_up(keys[sponsor_key]["address"])
    values = listing_values(
        currency, system["sc_uri"], system["custody_uri"],
        system["params_uri"], system["vault_uri"], system["liq_uri"],
        system["savings_uri"], system["psm_uri"], system["buffer_uri"],
        system["params_hash"], sponsor)
    listing_sig = listing_signature(keys[sponsor_key]["secret"], *values)
    listed = one(full_register_term(
        registry_uri, currency, system["sc_uri"], system["custody_uri"],
        system["params_uri"], system["vault_uri"], system["liq_uri"],
        system["savings_uri"], system["psm_uri"], system["buffer_uri"],
        system["params_hash"], sponsor, signature=listing_sig),
        keys[sponsor_key]["secret"])
    system["listed"] = listed
    system["entry"] = listed[1] if listed and listed[0] is True else None
    return system


# ---------------------------------------------------------------------------
# Extension points for T2/T3/T4
#
# The sibling terms do not exist in this branch. When they land:
#
#   * replace `render_legacy` with `render_vault` (T2), `render_buffer_savings`
#     (T3) and `render_psm` (T4), each with its own pin placeholders;
#   * deploy them after T1 and before provisioning, and take their published
#     component URIs from the deploy result;
#   * pass `renderers={"vault": ..., "buffer_savings": ..., "psm": ...}` to
#     `deploy_currency_system`. Each renderer receives keyword pins
#     (`root`, `currency`, `sc_uri`, `params_uri`, `issuer_shop_uri`,
#     `buffer_shop_uri`) and returns a deploy term. Result conventions:
#       vault           -> [vaultUri, liquidationUri, vaultAcceptUri,
#                           liquidationAuthLedgerUri]
#       buffer_savings  -> [savingsUri, bufferUri, bufferShopUri]
#       psm             -> [psmUri]
#     T2's `VaultAccept` URI is what `provision_facets` receives as its
#     consumer endpoint.
#   * provision T2 with `T2_KINDS` (four issuer kinds plus buffer), T4 with
#     `T4_KINDS`, and T3 with `T3_KINDS`; each call is one deploy because both
#     shops are called in the same term;
#   * register the eight URIs from the five terms instead of the composition
#     below.
#
# The kind groups above, the canonical provision payload and the listing
# preimage are the frozen interface; only the renderers and consumers change.

T2_ACCEPT_CONTRACT = "VaultAccept"

TERM_RENDERERS = {
    "T5_params": render_params_term,
    "T1_issuer": render_issuer,
    "T2_vault": render_vault,
    "T3_buffer_savings": render_buffer_savings,
    "T4_psm": render_psm,
}
