# Status

**The v0.5 economics and UI build is implemented; the behavioural campaign has not run.**
This tree is devnet-only; there are no real funds, no public testnet and no audit.

## What is implemented

| Area | Result |
|---|---|
| Kernel | Root, Clock, Verifier, Codec, Bounds, AdminGuard, Governor, the pure maths and ClaimCode |
| Stablecoin issuer | Per-currency systems created by one signed deploy: `Stablecoin`, `CollateralCustody`, `RiskParameters`, `VaultBook`, `LiquidationEngine`, `SurplusBuffer`, `SavingsPool`, `PegStabilityModule`; v2 params include the savings share and PSM fee |
| Economics | Repay splits principal and interest through `Stablecoin.settle`; interest reaches the surplus buffer, `cover(0)` absorbs outstanding `sin`, and `paySavings` moves the configured share to the pool in the same deploy; liquidation write-offs book `badDebt`/`sin` and halt minting while `sin > surplus`; PSM fees apply on both sides and `stableDebt` is signed |
| Governance | 2-of-3 admin actions; `schedule`/`execute` with a 100-block timelock for risk params, savings share and PSM policy; immediate currency pause and market status; `pending` view |
| Accounts | One account per owner; owner-gated purses; deposit facet; per-asset resolution; `accountState` holds the transfer counter and opId ledger; `transfers` history arm |
| Transfers | Measured send, book bounds, memo (128 bytes), opId idempotency with pending/completed replay, optional native-REV stipend for the claimer, claim/refund exclusivity |
| Markets | v4 25-field terms enforced by Bounds, the factory, the index and the pool; slug uniqueness; sponsor-owner and lock-beneficiary checks; activation seed/depth/share checks; tradability gate wired into swap; LP exit allowed while paused/delisted; `ListingViews.currencies`/`markets` |
| Clients | Rust SDK and CLI expose vaults, savings, PSM, buffer, risk params, markets, transfers and governance; WASM exposes the same user-facing surface; `rcash devnet demo` is a send → claim journey |
| Web | Accounts (chain-discovered currencies), Pay (memo/opId/stipend/journal), Claim, Vault, Earn, Redeem, Markets (list + create), Convert, Liquidity (non-zero minimums), History (journal + refund), Governance (read-only), Settings |
| Static gates | Contract build/measure/architecture/capture, market-term vectors, Rust fmt/clippy/build, wasm32 check, web typecheck/build and language policy are green |
| Behavioural campaign | Not yet run. The gate is `docs/SPEC.md` §20 and the plan: every specification item implemented first, then one fresh-devnet campaign with a per-requirement result |

The stablecoin design is DAI-shaped: REV-only collateral, per-currency systems, MCR,
interest, liquidation, a surplus buffer that absorbs bad debt, a savings pool and a PSM.
There is no recapitalisation token, no debt auction and no MKR analogue; a post-liquidation
shortfall is an accounting residual. Bridged BTC/ETH collateral is a separate future
workstream.

## Public testnet (rhobot)

The v0.4 platform terms were deployed to `testnet.rhobot.net` from a dedicated key funded
by the node faucet. Installed: Root, kernel, Bounds, Governor, the pure maths, oracle
registry and hub, currency registry and stablecoin directory, asset resolver, transfer
book, pool template, the market layer and the account factory. The generated manifest is
`deployments/testnet-v4.json`; the procedure is in [`TESTNET.md`](TESTNET.md).

**The rhobot validators run on 1 GB hosts; the advised memory is 8–16 GB.** Under the
deploy burst the hosts exhausted memory and the APIs became unresponsive (health
`nodes: 0`, `mem_available_mb` in single digits), with read lag and a later height
divergence between validators. Those observations are attributed to hardware below the
minimum advisory, not to the protocol; the local devnet (47 GB, 24 cores) is the
adequately provisioned evidence for the eight contract suites. The installer still
verifies every component with `Root.resolve` and re-registers missing keys as a safety
measure.

Feed listing and the TUSD stablecoin were not completed before the hosts became
unusable. Restarting the units does not fix the condition; the hosts need resizing to at
least 8 GB (16 GB+ ideally), and the same deploy should then be re-run there. The
failure mode is tracked upstream in
[rhovision-org/rholo#420](https://github.com/rhovision-org/rholo/issues/420).

## Legacy v0.1 results

The v0.1 payment scenarios (accounts, oracle, pool, transfer/claim/refund) remain as
historical evidence. The CDP and liquidation results are removed with the old CDP code.

The packaged demo is `rcash devnet demo` (fund → send a claimable REV transfer → claim).
The full behavioural campaign runs from a fresh devnet after the specification gate.

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

**R1 (typed reads) is complete for the legacy v0.1 surface.** `rcash` reads the oracle,
the FX pool (`quote`, `quoteAdd`, `reserves`, `params`, `pair`, LP asset), transfer
records (`info`, `nextId`, `quote`), native REV balances, and an account's balances in
one signed deploy. Vault and zone-vault reads are removed with the old CDP.

**R2 (protocol writes) is complete for the legacy v0.1 surface.** The CLI can fund an
Account, add/remove liquidity, swap/convert, send/claim/refund transfers, and submit
signed reporter prices. Vault and borrow commands are removed; `devnet demo` is retired
until the v0.4 payment journey is built.

A platform finding changed the read design: `explore-deploy` runs with no block context
(`rho:block:data` returns height 0), so every freshness-gated read must be a signed deploy.
The CLI does that; the SDK keeps public variants only for values that do not depend on
freshness. Documented in `CLIENT.md`.

**R3 (wasm wallet and React UI) is complete for the payment screens.** `crates/rcash-wasm`
exposes the wallet, encrypted Web3 v3 keystore and the SDK operations; `web/` is a React +
Vite + TypeScript app with Accounts, Receive, Convert, Pay, Claim, Liquidity and Settings.
The Mint screen and vault operations are removed. Batch and Ramps remain disabled. The
browser journey will be rebuilt for the v0.4 payment flow.

Secrets never reach the DOM: the key stays in wasm, the keystore is encrypted into
IndexedDB, and a claim secret lives only in the URL fragment.

**v0.4 SDK, CLI, WASM and web are in place.** `deployments/devnet-v4.json` names the installed components; the CLI `v4` group covers currency/market/slot/reserves/supply reads and account funding, send/claim/refund, swap, add-and-lock, LP release and vault mint/repay/withdraw. The wasm facade exposes the same methods plus `claim_hash`, `public_key` and `height`, and the React screens use them. The send/claim/refund journey was driven end to end through the CLI on a fresh devnet.

**R4 (CI and docs) is in place.** GitHub Actions runs the Rust format/clippy/tests, wasm
build and tests, the web typecheck/unit/build, and a contracts-drift check without Docker.
The browser journey is a manual workflow because it needs a running devnet.

Next: retire the Python harness, public testnet and an external audit before any real
funds.

## Specification

`docs/INTENT.md` is the product intent. `docs/spec/` is the normative v0.4 core
specification; `docs/SPEC.md` is the v0.1 legacy reference. The v0.4 component catalogue
is `contracts/components.json`.

## Platform constraints that shaped the build

- Deploy term limit 65,536 bytes; parser depth 128; the bundle free-variable check. Singleton
  components are registered by URI in Root and resolved at arm entry; only locally created
  capabilities are captured in bundles.
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
- The v0.4 stablecoin issuer is REV-only; REV volatility can produce bad debt, and the
  issuer must enforce MCR, close factor and bad-debt accounting. Bridged collateral is a
  separate future workstream.
- Ramps are off-chain and unbonded; local fiat payout is a trust decision.
- Claim secrets are bearer authority; loss is unrecoverable before expiry.
- The chain is pre-testnet (rholo #242); this is not safe for real value.
