#!/usr/bin/env python3
"""Exercise the external-asset registry seam.

Deploys a fake bridge adapter that exposes the documented issuer/brand/attest
interface, registers it as USDC, checks AssetResolver, and refuses a 6-decimal
adapter. No bridge or custody is involved.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import sign_payload  # noqa: E402
from mesh_support import load_env  # noqa: E402
from unit_v3 import call, check, faucet_top_up, one  # noqa: E402

ADAPTER = """new ExternalAsset, rl(`rho:registry:lookup`), ertpCh, kitCh,
  uriCh, rs(`rho:registry:insertArbitrary`), deployId(`rho:rchain:deployId`)
in {
  rl!(`rho:rchain:ertp`, *ertpCh) |
  for (@(_, ERTP) <- ertpCh) {
    @ERTP!("makeIssuerKit", *kitCh) |
    for (@(brand, mint, issuer) <- kitCh) {
      contract ExternalAsset(@"attest", ret) = {
        ret!((true, {"asset": "__CODE__", "kind": "external",
                     "sponsor": "__SPONSOR__", "decimals": __DECIMALS__,
                     "brand": "__BRAND__", "issuer": "__ISSUER__",
                     "chain": "test", "custodian": "test"}))
      } |
      contract ExternalAsset(@"issuer", ret) = { ret!((true, issuer)) } |
      contract ExternalAsset(@"brand", ret) = { ret!((true, brand)) } |
      rs!(bundle+{*ExternalAsset}, *uriCh) |
      for (@uri <- uriCh) { deployId!([uri]) }
    }
  }
}"""


def deploy_adapter(keys: dict, code: str, decimals: int) -> tuple[str, str, str]:
    sponsor = keys["sponsor"]["public"]
    brand = f"{code}-brand"
    issuer = f"{code}-issuer"
    term = (ADAPTER.replace("__CODE__", code)
            .replace("__SPONSOR__", sponsor)
            .replace("__DECIMALS__", str(decimals))
            .replace("__BRAND__", brand)
            .replace("__ISSUER__", issuer))
    return one(term, keys["deployer"]["secret"])[0], brand, issuer


def register(keys: dict, state: dict, code: str, adapter: str,
             brand: str, issuer: str):
    sponsor = keys["sponsor"]
    payload = sign_payload.canonical(
        "rcash:external-asset-register:v3",
        [code, adapter, brand, issuer, sponsor["public"]])
    sig = sign_payload.sign_payload(sponsor["secret"], payload.encode())["signature"]
    body = (
        f'CurrencyRegistry!("registerExternal", "{code}", "{adapter}", '
        f'"{brand}", "{issuer}", "{sponsor["public"]}", "{sig}".hexToBytes(), '
        "*deployerId, *r) |\n"
        "  for (@x <- r) { deployId!(x) }"
    )
    term = (
        "new rl(`rho:registry:lookup`), ch, r, "
        "deployerId(`rho:rchain:deployerId`), "
        "deployId(`rho:rchain:deployId`) in {\n"
        f"  rl!(`{state['currency_registry_uri']}`, *ch) |\n"
        f"  for (CurrencyRegistry <- ch) {{ {body} }}\n"
        "}"
    )
    # OCAP-11: the sponsor key must submit the listing.
    return one(term, sponsor["secret"])


def main() -> int:
    keys, state = load_env()
    faucet_top_up(keys["sponsor"]["address"])
    adapter, brand, issuer = deploy_adapter(keys, "USDC", 8)
    reply = register(keys, state, "USDC", adapter, brand, issuer)
    check("external registered", reply[0], True)
    check("external kind", reply[1].get("kind"), "external")
    check("external decimals", reply[1].get("decimals"), 8)

    entry = one(call(state["currency_registry_uri"], "CurrencyRegistry",
                     'CurrencyRegistry!("currency", "USDC", *r) | '
                     "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    check("external lookup kind", entry[1].get("kind"), "external")
    check("external lookup uri", entry[1].get("assetUri"), adapter)

    kind = one(call(state["asset_resolver_uri"], "AssetResolver",
                    'AssetResolver!("kind", "USDC", *r) | '
                    "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    check("resolver kind", kind, (True, "external"))
    issuer = one(call(state["asset_resolver_uri"], "AssetResolver",
                      'AssetResolver!("issuer", "USDC", *r) | '
                      "for (@x <- r) { deployId!(x) }"), keys["deployer"]["secret"])
    check("resolver issuer", issuer[0], True)

    bad, bad_brand, bad_issuer = deploy_adapter(keys, "USDX", 6)
    refused = register(keys, state, "USDX", bad, bad_brand, bad_issuer)
    check("6-decimal adapter refused", refused, (False, "external decimals"))

    duplicate = register(keys, state, "USDC", adapter, brand, issuer)
    check("duplicate external refused", duplicate[0], False)
    print("unit_external: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
