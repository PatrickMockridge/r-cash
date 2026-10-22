# Status

**Phases 0-4 core are implemented and passing on the local devnet.** This is still a devnet-only
prototype; no real funds and no public testnet.

## Measured results

| Area | Result |
|---|---|
| Phase-0 capability gates | **12/12** — persistence, rollback of tuple space and native ERTP/REV, ERTP purse across blocks, REV round-trip, deployerId containment, registry, clock, signatures, claim hash, cost/finality |
| Accounts and Directory | **7/7** — two keys, owner-only withdrawal, unauthorized refusal, Directory lock |
| Oracle | **19/19** — signed reporter prices, median, freshness, spread, cross rate, 2-of-3 admin, replay rejection, staleness |
| CDP / CurrencyZone | **19/19** — open, collateral, borrow, MCR limits, repay, interest, health, withdrawal limits |
| Liquidation | **17/17** — price drop, liquidatable vault, permissionless liquidation, debt/collateral accounting |
| rNGN/rKES FxPool (FPMM) | **14/14** — add liquidity, LP tokens, swap both directions, reserves, remove liquidity |
| Transfer/claim/refund | **7/7** — send with claim hash, recipient claim, expired-transfer refund |

## Packaged demo

`make demo` on a fresh devnet exits **0**: the bootstrap, pool setup, FxPool deploy, TransferBook
deploy, pool scenario (14/14) and transfer scenario (7/7) all pass. The deploy scripts write
`deployments/devnet.json` with the Directory, AccountFactory, OracleHub, zone, Components and pool
URIs/installation markers.

## What works end to end

1. A key opens an Account (non-custodial, per-key).
2. The Account can hold REV, rNGN, rKES and LP tokens.
3. A REV holder opens NGN/KES vaults, deposits collateral, borrows local stablecoin, repays, and is
   liquidated if the oracle price drops below MCR.
4. The rNGN/rKES FPMM quotes at the median oracle rate with a spread and inventory skew; LPs earn it.
5. A sender sends local currency with a claim hash; the recipient claims with the secret; an
   expired transfer refunds to the sender.

## Client migration

**R0a (signature parity) is complete.** The repo now carries a Rust workspace
(`rcash-core`, `rcash-chain`, `rcash-sdk`, `rcash-cli`, `rcash-wasm`) and an AGPL-3.0-only
license.

- A Rust-signed deploy was accepted, processed and finalized by the local devnet.
- Parity is byte-identical across Rust native, wasm32 and an independent TypeScript signer
  for encoded DeployData bytes, public key, DER signature and REV address.
- The node's own REV-address and secp256k1 known-answer vectors are pinned as tests.
- Two platform facts discovered during the work are documented in `CLIENT.md`: the shard
  id is `/root`, and `validAfterBlockNumber` anchors the 50-block lifespan, so a deploy
  anchored at 0 is never proposed.
- The `rcash` CLI can generate devnet keys, read node status, deploy/explore terms, poll
  status and use the faucet.
- MetaMask is **read-only** in the supported path; the `secp256k1:eth` signing spike is
  specified but not run (`SPIKE-METAMASK.md`).

**R1 (typed reads) is complete.** `rcash` reads live devnet state for the oracle
(`get`, `getPair`, reporters), the FX pool (`quote`, `quoteAdd`, `reserves`, `params`,
`pair`, LP asset), currency zones (`vault`, `vaults`, `params`, `supply`, brand/issuer/
currency), transfer records (`info`, `nextId`, `quote`), native REV balances, and an
account's balances in one signed deploy. The fixed-point math module mirrors the SPEC
formulas with the seeded-vault vectors pinned as tests.

**R2 (protocol writes) is complete.** The CLI can fund an Account, open/operate NGN and
KES vaults, add/remove liquidity, swap/convert, send/claim/refund transfers, and submit
signed reporter prices. `rcash devnet demo` runs the acceptance journey and exits 0:
oracle refresh, funding, both vaults, borrow, liquidity add/remove, convert, send+claim,
send+refund, and balance readback (10 steps).

A platform finding changed the read design: `explore-deploy` runs with no block context
(`rho:block:data` returns height 0), so every freshness-gated read must be a signed deploy.
The CLI does that; the SDK keeps public variants only for values that do not depend on
freshness. Documented in `CLIENT.md`.

Next: R3 wasm wallet and the React UI, R4 docs/CI and legacy-harness retirement.

## Specification

`docs/INTENT.md` is the product intent; `docs/SPEC.md` is the normative v0.1 specification. The spec
marks the implemented arms and separates them from planned components; the Components registry is
locked by the TransferBook deploy so no later caller can redirect the pool or book.

## Platform constraints that shaped the build

- Deploy term limit 65,536 bytes; parser depth 128; the bundle free-variable check. Large contracts
  (pool, transfer book) are deployed in separate terms and their live names are held in
  `ComponentRegistry` instead of a bundle.
- BigInt intermediates require `.toInt()` at fixed-point boundaries.
- Name/value quoting and duplicate binder rules in Rholang are strict; see `PLATFORM.md`.

## Not in this build (deferred)

- CPMM backup venue, Router best-of-two.
- Batch payouts, PaymentRequests/invoices.
- RampRegistry contract and a mock ramp script (the recipient key claims in the transfer test; the
  off-chain payout leg is documented, not implemented).
- Direct-delivery transfers (claim-link only), multi-hop routing, OTC limit orders/RFQ.
- User CLI/SDK, web UI, public-testnet deployment, external audit.

## Honest risks

- Oracle is a 3-reporter committee; the pool/book pause on stale feeds.
- REV collateral is volatile; liquidation has no stability-pool backstop.
- Ramps are off-chain and unbonded; local fiat payout is a trust decision.
- Claim secrets are bearer authority; loss is unrecoverable before expiry.
- The chain is pre-testnet (rchain-rust #242); this is not safe for real value.
- The liquidation path uses the oracle's median and the vault view reports `fresh`; the keeper must
  check freshness. A stale feed can make the vault view report liquidatable while the payout helper
  refuses; the keeper should treat both `fresh=false` and refusal as "do not liquidate".
