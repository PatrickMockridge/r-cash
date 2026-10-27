# The R-Cash currency network

Local currencies are nodes; direct pools are edges. A **corridor** is a directed edge, e.g.
NGN→KES, with a pool, an oracle pair and a set of on/off-ramp partners.

## Launch set

| Currency | Asset id | Stablecoin | Status |
|---|---|---|---|
| Nigerian naira | `NGN` | rNGN | launch |
| Kenyan shilling | `KES` | rKES | launch |
| Ghanaian cedi | `GHS` | rGHS | phase 5 template proof |
| Others | `ZAR`, `UGX`, … | rXXX | same template |

NGN↔KES is the launch corridor. NGN↔GHS proves that adding a currency is configuration, not new
product code.

## Adding a currency

1. Deploy `31_stablecoin` with the sponsor's signed v2 params. The one deploy creates the
   issuer, custody, risk parameters, vault book, liquidation engine, surplus buffer,
   savings pool and PSM, and returns eight URIs.
2. Register the system in `CurrencyRegistry`/`StablecoinDirectory` with the sponsor
   signature over the v3 payload (all eight URIs, params hash and sponsor) and the live
   attestation; `AssetResolver` derives the asset metadata.
3. Add reporter prices for the new code (signed `oracle.submit`) and bind the feed.
4. Create the market with `MarketFactory.createMarket` from sponsor-signed 25-field terms,
   seed it, fund the lock and activate it (or trade through the PSM alone).
5. Seed liquidity from the issuer, an LP, or the PSM's REV buffer.

No new product code is required: `TransferBook`, `FxPool`, `SavingsPool`,
`PegStabilityModule` and the clients resolve the new currency through the registries.
On/off-ramp partners are outside this scope; there is no `RampRegistry`.

## Direct pairs only (for now)

The winner of the corridor model is that there is no mandatory USD hop. The cost is that a pair needs
a direct pool to be usable. The MVP's Router refuses a pair without a direct pool
(`(false, "no direct pool")`).

Multi-hop routing is deliberately deferred: a failed second hop after a first hop committed is a lost
intermediate payment unless a two-phase/escrow pattern is proved. Until then, add the direct pool.

## Pool choice

- **FxPool (FPMM)** is the default for pegged FX (NGN/KES, NGN/GHS). It quotes at the oracle rate
  plus a spread, with an inventory-skew charge and a max-trade limit. LPs earn the spread; the pool
  does not rely on arbitrage to find the rate.
- **CpmmPool** is the permissionless backup venue: anyone can add a pair, and the Router picks the
  better direct quote. It is also useful when a pair's oracle is paused.
- The Router compares the direct quotes and executes the better one. It never splits a payment across
  venues in the MVP.

## Ramps

A corridor is only as useful as its last mile. `RampRegistry` lists on-ramp and off-ramp partners per
corridor:

- **On-ramp**: the partner takes fiat locally, sends the local stablecoin to the user's Account.
- **Off-ramp**: the partner redeems a claim with its secret, then pays mobile money/cash.

The MVP allowlists ramps and has no bond. A bonded/permissionless ramp registry, dispute windows and
slashing are later phases. Until then, ramp selection is a trust decision, displayed as such.

## Fees

The pool spread is the protocol-level fee and goes to LPs. The ramp's payout fee is off-chain and
displayed by the ramp. The protocol has no transfer fee in the MVP; a fee switch is explicit later.
