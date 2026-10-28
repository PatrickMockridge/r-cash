# External assets (bridged USD and similar)

R-Cash can list an asset that is not issued by its own REV-collateralised
stablecoin system. The first use is bridged DAI/USDC/USDT-style USD. **This
document does not define a bridge.** It defines the adapter interface a bridge or
custodian must satisfy so the registry, asset resolver and DEX can treat the
asset as a standard ERTP asset.

## 1. What the registry needs

`CurrencyRegistry!("registerExternal", code, assetUri, sponsorHex, sig, ret)`:

1. verifies the sponsor signature over
   `rcash:external-asset-register:v1|code|assetUri|sponsor`;
2. calls `assetUri!("attest")` and requires
   `{asset: code, kind: "external", sponsor: sponsorHex, decimals: 8}`;
3. refuses a code that already exists;
4. writes an entry
   `{kind: "external", assetUri, decimals: 8, sponsor, status: "active"}`
   to the directory and the currency map.

`AssetResolver!("issuer", code, ret)` resolves the entry, calls
`assetUri!("issuer")` and `assetUri!("brand")`, and returns
`(true, brand, issuer)`. An adapter with `decimals != 8` is refused at
registration with `"external decimals"`; the bridge must normalise to 1e8 ERTP
base units.

## 2. Adapter interface

A bridge, custodian or wrapped-asset issuer deploys one contract per asset with
its ERTP issuer and brand in closure:

```rholang
contract ExternalAsset(@"attest", ret) = {
  ret!((true, {
    "asset": "__CODE__",
    "kind": "external",
    "sponsor": "__SPONSOR_PUB__",
    "decimals": 8,
    "chain": "__SOURCE_CHAIN__",
    "custodian": "__CUSTODIAN__"
  }))
} |
contract ExternalAsset(@"issuer", ret) = { ret!((true, *issuer)) } |
contract ExternalAsset(@"brand", ret) = { ret!((true, *brand)) }
```

The adapter is deployed by the bridge/custodian with `issuer` and `brand` closed
over. R-Cash does not mint, burn, redeem, bridge or custody the underlying asset.
The adapter is the whole trust boundary.

## 3. Market and pool behaviour

An external asset trades exactly like a stablecoin in `FxPool`: the pool deposits
and withdraws through the ERTP issuer returned by `AssetResolver`. It needs:

- its own oracle feed (`OracleRegistry` one feed per code);
- a registered external entry before a market can resolve it;
- a market created through `MarketFactory` like any other pair.

External assets have no VaultBook, PSM, savings pool or liquidation engine.
`Vault`, `Earn`, `Redeem` and the stablecoin-only governance screens MUST filter
them out. `Accounts`, `Pay`, `Convert`, `Liquidity` and `Markets` include them and
label them `external`.

## 4. Risk and kill switches

- The sponsor attestation is the only provenance claim. R-Cash makes no
  solvency, redemption or reserve claim for an external asset.
- The UI shows `external`, the custodian/chain from the attestation, and the
  sponsor.
- `CurrencyRegistry.setPaused` for an external entry is governor-authorised and
  sets the registry status; `MarketIndex.pauseAsset` pauses every active market
  whose base or quote is the code. Both are immediate governance actions.
- A depegged asset is priced by its own oracle feed; the DEX must not assume 1.0
  for a bridged USD. The native R-Cash USD feed is the 1.0 reference.
- The bridge adapter must normalise decimals to 8. An adapter that cannot is not
  listable.

## 5. Explicitly deferred

- Cross-chain lock/mint, relayer, attestation or light-client verification.
- Reserve attestations beyond the sponsor signature.
- Automatic redemption between native USD and a bridged USD variant.
- Treating two USD variants as the same accounting unit. They are separate codes
  with separate feeds, balances and markets.
