# Status

**The v0.4 payment-first reset is in progress.** The old CDP is deleted; the kernel,
oracle and governor layers are retained. This is still a devnet-only prototype; no real
funds and no public testnet.

## v0.4 payment-first reset (Phase 0)

The product is a decentralised TransferWise, not a lending platform. The old CDP,
vault, collateral and Mint surfaces are deleted from the active contracts, tests,
docs, SDK, CLI, WASM, web app and TLA models. The kernel, oracle and governor layer
is retained; the composable REV-backed stablecoin issuer and the payment layer are
the next build.

| Area | Result |
|---|---|
| Deleted | v0.1/v0.2/v0.3 CDP contracts, vault arms, CDP tests/scenarios, `CdpAccounting` TLA, SDK/CLI/WASM vault methods, web Mint screen, CDP docs sections |
| Retained | Root, Clock, Verifier, Codec, Bounds (with `checkIssuer`), AdminGuard, Governor, AmmMath, OracleMath, ClaimCode, OracleRegistry/Feed/Hub, AccountFactory account capability |
| Stablecoin issuer | `Stablecoin`, `CollateralCustody`, `RiskParameters`, `VaultBook`, `CollateralMath`, `LiquidationEngine`; signed params, bounded risk, mint/repay/withdraw, REV custody, partial liquidation and bad-debt write-off |
| Listing | `CurrencyRegistry` + `StablecoinDirectory`: sponsor signature, live attestation, one system per currency, governor-gated pause |
| Accounts | `AccountFactory` creates an `Account`, `PurseStore` and `AccountGate` per owner; `AssetResolver` maps `REV` and listed currencies to brand/issuer; deposit, withdraw, balance and deposit-facet; owner check by caller `deployerId`; the vault proof stays in the account closure |
| Issuer checks | system deploy, attestations, supply, params, custody, open → deposit REV → mint → repay → withdraw; partial liquidation, underwater write-off, the debt/bad-debt conservation invariant and the liquidation-capability refusal all pass on the devnet |
| Account checks | key-signed deposit via deposit facet, balance, withdraw, empty stablecoin purse through the registry, and a foreign deployer refused by `AccountGate` |
| Transfers | `TransferBook` allocates ids and creates a per-transfer `TransferContract`; claim by secret preimage, refund after expiry by the sender, wrong-secret and foreign-refund refusals, and closed-terminal refusals all pass |
| Markets | `MarketTerms` + `MarketIndex` + `MarketDirectory` + `MarketFactory` (`50_market`) with `PoolTemplate`/`assemblePool`/`LiquidityLock` (`51_pool`); a REV/V4T market is created from sponsor-signed terms, seeded from a vault-backed account, the seed LP locked, the market activated and swapped at the oracle rate minus the spread; after the lock height the beneficiary releases the seed and removes the liquidity; listings expose read-only views (`ListingViews`), a pure `TradabilityGate`, governor-gated pause/resume/delist, and a v2 draft staged after delist |
| Gates | build, measure, architecture, capture, language and TLA gates pass; the old capture finding is gone |
| Live client flow | CLI drove vault-mint → add-and-lock → activate → swap on a seeded v2 market: 0.01 REV produced 74,775,747 V4T base units and the reserves moved exactly |
| Browser journey | Playwright creates two wallets, faucets them, funds the sender, sends a claimable transfer, claims it in the recipient context and sees the 0.01 REV purse credit (52.8 s) |
| Next | public testnet and an external audit |

The stablecoin design is DAI-like: REV-only collateral, per-currency systems, MCR,
interest, liquidation and bad debt, with separate contracts per authority. Bridged
BTC/ETH collateral is a separate future workstream. There is no borrower-facing
lending UI, yield product or credit market.

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
least 8 GB (16 GB+ ideally), and the same deploy should then be re-run there.

## Legacy v0.1 results

The v0.1 payment scenarios (accounts, oracle, pool, transfer/claim/refund) remain as
historical evidence. The CDP and liquidation results are removed with the old CDP code.

No packaged demo runs during the v0.4 reset; the fresh v0.4 install and payment
journey land with the new issuer and payment layers.

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
- The chain is pre-testnet (rchain-rust #242); this is not safe for real value.
