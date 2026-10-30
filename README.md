# R-Cash

**A permissionless multi-currency account and cross-border payments network on
[rholo](https://github.com/rhovision-org/rholo).**

R-Cash is the on-chain payments core of a Wise-shaped product. You can hold local-currency
balances, receive money as if you had a local account, convert directly between currencies,
and pay anyone — with a wallet or a claim link. Liquidity providers, not correspondent banks,
earn the FX spread.

The protocol issues a local stablecoin per currency, runs a DAI-shaped issuer to keep it
credible (vaults, interest, liquidation, a surplus buffer, savings and a peg stability
module), and provides a full mesh of direct FX markets. The core loop is **hold → receive →
convert → pay → get paid**.

## Documentation

The book is the human-readable explanation: start with
[**What is R-Cash?**](book/src/index.md), then follow the parts in order.

```sh
make docs        # build to book/book
make docs-serve  # serve at http://localhost:3000
make docs-check  # build and check links
```

The normative specification stays in [`docs/SPEC.md`](docs/SPEC.md) and
[`docs/spec/`](docs/spec/). The book explains and links; it does not replace them. If you are
an AI coding agent, read [`AGENTS.md`](AGENTS.md) first.

## Status at a glance

R-Cash is a **v0.5, devnet-only prototype**. There is no fiat custody, no real value, no audit
and no mainnet deployment. The rholo chain is pre-testnet.

| Area | State |
|---|---|
| Contracts | Kernel, oracle, per-currency stablecoin issuer, buffer, savings, PSM, markets, accounts and transfers implemented |
| Clients | Rust SDK and CLI, WASM facade, React web app |
| Static gates | Green: contract build/measure/architecture/capture, market-term vectors, Rust fmt/clippy/tests, wasm32, web typecheck/build, language policy |
| Devnet campaign | 13 behavioural suites and the CLI demo passed on a fresh fixed-node devnet on 2026-10-27; mesh and external-asset suites were added afterwards |
| Public testnet | Rebuilt 2026-10-29. The 2026-10-28 campaign was blocked by the operator's resource-admission throttle, not by a contract result; it has not been re-run as a full campaign |
| Audit / mainnet | Not done. Do not use with real funds |

The [status chapter](book/src/orientation/status-and-scope.md) explains the evidence and the
exclusions.

## Quickstart

Prerequisites: Docker, Python 3.12, Node 22, and an rholo checkout (set `RHOLO_DIR`; it
defaults to `../rholo`).

```sh
make venv                 # .venv + harness deps
make image                # build rnode:local (once; slow)
make setup                # devnet + keys + install + bootstrap
make probes               # phase-0 capability gates
make demo                 # Rust client send -> claim journey
make down                 # stop and drop the devnet
```

`make setup` chains `devnet`, `keys`, `install` (the chain-aware, signed-read installer) and
`bootstrap` (the stablecoin and market acceptance suites). Systems and markets are discovered
through `ListingViews`; there is no separate systems manifest.

The web client is React + Vite + TypeScript over the same Rust SDK compiled to WASM:

```sh
cd web
npm install
npm run dev        # builds the wasm module and serves http://localhost:5173
npm run test:e2e   # Playwright journey against the running devnet
```

## Architecture

- `Account` — non-custodial, per-key; owner-gated purses, vault access, transfer ops and the
  opId ledger.
- Per-currency issuer cluster (`31_stablecoin`) — `Stablecoin`, `CollateralCustody`,
  `RiskParameters`, `VaultBook`, `LiquidationEngine`, `SurplusBuffer`, `SavingsPool`,
  `PegStabilityModule`; one signed deploy, because mint/burn/settlement capabilities cannot
  cross a deploy boundary.
- `FxPool` + `LiquidityLock` (per market) — oracle-anchored pool, LP tokens, spread and skew,
  one-shot seed lock.
- `OracleHub` — three allowlisted reporters, median, freshness, spread, signed policy.
- `TransferBook` + `TransferContract` — measured send, memo/opId, claim, expiry, refund, one
  terminal state per transfer.
- `Root`, `CurrencyRegistry`, `StablecoinDirectory`, `OracleRegistry`, `MarketDirectory`,
  `MarketIndex`, `ListingViews` — discovery and lifecycle.
- `Governor` — 2-of-3 secp256k1 signatures, per-domain nonces and a 100-block timelock for
  parameter changes; emergency pause and market status are immediate.

## Client stack

The client is Rust, shared by a native CLI and a browser WASM module:

- `crates/rcash-core` — amounts, validated identifiers, Rholang quoting, the manifest.
- `crates/rcash-chain` — deploy encoding, secp256k1 signing, REV addresses, the rholo node
  HTTP client, deploy-status polling, hostlist discovery and node pools.
- `crates/rcash-sdk` — connected client and protocol operations.
- `crates/rcash-cli` — the `rcash` binary.
- `crates/rcash-wasm` — wasm-bindgen facade for the React + Vite + TypeScript UI.

Signature parity with the node is a blocking gate and is green: the node's REV address and
secp256k1 vectors, DeployData golden bytes, an independent TypeScript signer, and wasm32 all
produce identical bytes.

The CLI/SDK consume the node's deploy hostlist when it publishes one: discovery is
feature-detected (a 404 means the seed and any known `--nodes` are used alone), reads
round-robin with failover, and writes choose one accepting node and send each signed deploy to
exactly one node, never re-submitted elsewhere. See [The CLI](book/src/guides/cli.md).

## Verification

- `make spec-check` — contract build, budgets, architecture and capture lint.
- `make formal-check` — Lean build/axiom audit, flow completeness, traceability, mesh gate.
- `make unit-all` — ordered behavioural suites on a devnet.
- `make pre-devnet-check` — the full static, Rust, WASM and web gate.

The formal models prove properties of a mathematical model, not of the deployed Rholang. The
behavioural suites run on a disposable chain. Neither is an audit. See
[How the protocol is verified](book/src/trust/verification.md) and
[Testing and the acceptance campaign](book/src/trust/testing.md).

## License

AGPL-3.0-only. Code committed through `d5d613b` was Apache-2.0; those grants are not revoked.
Third-party notices — including the pinned AGPL-3.0 node crates and the Apache-2.0 RhoGov
signer used as a parity reference — are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
