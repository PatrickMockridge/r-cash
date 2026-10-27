# R-Cash

A permissionless multi-currency account and cross-border payments network on
[rholo](https://github.com/rhovision-org/rholo).

R-Cash is the on-chain payments core of a Wise-shaped product: hold local-currency balances,
receive as if local, convert directly between currencies, pay anyone with a wallet or claim link,
and get paid — while liquidity providers earn the FX spread.

## What works today (v0.5)

| Area | Result |
|---|---|
| Kernel and oracle | Root, Clock, Verifier, Codec, Bounds, Governor (timelock), per-currency feeds, hub cross-rates |
| Stablecoin issuer | REV-collateralised per-currency stablecoins with signed v2 params (including the savings share and PSM fee), vaults, interest, liquidation, bad debt |
| DAI-style loop | Repay splits principal and interest; the surplus buffer absorbs bad debt (`sin`), halts minting when short, and pays the configured savings share on every repay; a per-owner savings pool and a signed-debt PSM provide par redemption and issuance |
| Accounts and purses | One account per owner, owner-gated purses, deposit facets, asset resolution through the registry, transfer op ledger |
| Transfers | Claimable per-transfer cells with measured payments, expiry, memo, opId idempotency, an optional native-REV stipend for the claimer, and exactly one terminal state |
| Markets | Signed v4 terms enforced end to end, factory-built pools, seed lock, activation seed checks, swaps through the tradability gate, LP exit while paused/delisted |
| Clients | Rust SDK and CLI, WASM facade and React screens for accounts, pay/claim/history, vault, savings, PSM redeem, markets, liquidity and governance |
| Verification | Static gates are green. The behavioural devnet campaign runs only after every specification item is implemented; see `docs/SPEC.md` for the traceability and the campaign report format. |

**Networks.** The local devnet (`make devnet`) is the harness target. The rhobot public
testnet is documented in [`docs/TESTNET.md`](docs/TESTNET.md) and is upstream-blocked. No
fiat custody and no real value; the chain is pre-mainnet.

## Client stack

The client is Rust, shared by a native CLI and a browser WASM module:

- `crates/rcash-core` — amounts, validated identifiers, Rholang quoting, the manifest.
- `crates/rcash-chain` — deploy encoding, secp256k1 signing, REV addresses, rholo node HTTP.
- `crates/rcash-sdk` — connected client and protocol operations.
- `crates/rcash-cli` — the `rcash` binary.
- `crates/rcash-wasm` — wasm-bindgen facade for the React + Vite + TypeScript UI (R3).

Signature parity with the node is a blocking gate and is green: the node's REV address and
secp256k1 vectors, DeployData golden bytes, an independent TypeScript signer, and wasm32
all produce identical bytes. See [`docs/CLIENT.md`](docs/CLIENT.md).

**Languages:** Rust, Rholang, Python and TypeScript. See
[`docs/LANGUAGES.md`](docs/LANGUAGES.md).

```sh
cargo build --workspace
cargo test --workspace --exclude rcash-wasm
cargo run -p rcash-cli -- deploy --term 'Nil' --key deployer
cargo run -p rcash-cli -- devnet demo
```

The web client is React + Vite + TypeScript over the same Rust SDK compiled to WASM:

```sh
cd web
npm install
npm run dev        # builds the wasm module and serves http://localhost:5173
npm run test:e2e   # Playwright journey against the running devnet
```

See [`docs/CLIENT.md`](docs/CLIENT.md) and [`docs/FRONTEND.md`](docs/FRONTEND.md).

`rcash devnet demo` funds the account, sends a claimable REV transfer to itself and claims
it. It is a smoke journey, not the full acceptance campaign.

## Quickstart

Prerequisites: Docker, Python 3.12, Node 22, and the rholo checkout (set `RHOLO_DIR`; it
defaults to `../rholo`).

```sh
make venv                 # .venv + harness deps
make image                # build rnode:local (once; slow)
make setup                # devnet + keys + install + bootstrap
make probes               # phase-0 capability gates
make demo                 # Rust client send -> claim journey
make down                 # stop and drop the devnet
```

`make setup` chains `devnet`, `keys`, `install` (the chain-aware, signed-read installer)
and `bootstrap` (the stablecoin and market acceptance suites, which leave the demo system
and the REV/V4T market on chain). Systems are discovered by clients through
`ListingViews`; there is no separate systems manifest.

## Architecture

- `Account` — non-custodial, per-key; owner-gated purses, vault access, transfer ops and the
  opId ledger.
- Per-currency issuer cluster (`31_stablecoin`) — `Stablecoin`, `CollateralCustody`,
  `RiskParameters`, `VaultBook`, `LiquidationEngine`, `SurplusBuffer`, `SavingsPool`,
  `PegStabilityModule`; one signed deploy, because mint/burn/settlement capabilities cannot
  cross a deploy boundary.
- `FxPool` + `LiquidityLock` (per market) — oracle-anchored pool, LP tokens, spread and
  skew, one-shot seed lock.
- `OracleHub` — three allowlisted reporters, median, freshness, spread, signed policy.
- `TransferBook` + `TransferContract` — measured send, memo/opId, claim, expiry, refund, one
  terminal state per transfer.
- `Root`, `CurrencyRegistry`, `StablecoinDirectory`, `OracleRegistry`, `MarketDirectory`,
  `MarketIndex`, `ListingViews` — discovery and lifecycle.
- `Governor` — 2-of-3 secp256k1 signatures, per-domain nonces and a 100-block timelock for
  parameter changes; emergency pause and market status are immediate.

## Docs

[`docs/INTENT.md`](docs/INTENT.md) — why, users, principles, scope and success criteria.
[`docs/SPEC.md`](docs/SPEC.md) — the normative v0.5 product specification with numbered
requirements, acceptance criteria and traceability; [`docs/spec/`](docs/spec/) — the formal
component calculus, invariant table and wiring.
[`docs/NETWORK.md`](docs/NETWORK.md) (corridors), [`docs/PLATFORM.md`](docs/PLATFORM.md) (pinned
node, hard limits, measured costs), [`docs/STATUS.md`](docs/STATUS.md) (verdict + deferred work),
[`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md), [`docs/LEGAL.md`](docs/LEGAL.md).

## License

AGPL-3.0-only. Code committed through `d5d613b` was Apache-2.0; those grants are not
revoked. Third-party notices — including the pinned AGPL-3.0 node crates and the
Apache-2.0 RhoGov signer used as a parity reference — are in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
