# R-Cash

A permissionless multi-currency account and cross-border payments network on
[rchain-rust](https://github.com/rhovision-org/rholo).

R-Cash is the on-chain payments core of a Wise-shaped product: hold local-currency balances,
receive as if local, convert directly between currencies, pay anyone with a wallet or claim link,
and get paid — while liquidity providers earn the FX spread.

## What works today (v0.4)

| Area | Result |
|---|---|
| Kernel and oracle | Root, Clock, Verifier, Codec, Bounds, Governor, per-currency feeds, hub cross-rates |
| Stablecoin issuer | REV-collateralised per-currency stablecoins: signed params, mint/repay, interest, liquidation, bad-debt write-off, sponsor-signed listing |
| Accounts and purses | One account per owner, owner-gated purses, deposit facets, asset resolution through the registry |
| Transfers | Claimable per-transfer cells: secret claim, expiry, sender refund, exactly one terminal state |
| Markets | Signed terms, factory-built pools, seed lock, activation, swaps, liquidity, views, tradability gate, governor-gated pause/delist |
| Clients | Rust SDK and CLI, WASM facade and React screens; a Playwright journey covers send → claim |
| Verification | Eight fresh-chain harness suites, Rust unit tests, wasm smoke, web typecheck/build and the browser journey |

**Networks.** The local devnet (`make devnet`) is the harness target. The rhobot public
testnet is documented in [`docs/TESTNET.md`](docs/TESTNET.md). No fiat custody and no real
value; the chain is pre-mainnet.

## Client stack

The client is Rust, shared by a native CLI and a browser WASM module:

- `crates/rcash-core` — amounts, validated identifiers, Rholang quoting, the manifest.
- `crates/rcash-chain` — deploy encoding, secp256k1 signing, REV addresses, rnode HTTP.
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

`rcash devnet demo` is the end-to-end client journey (oracle, vaults, liquidity, convert,
send/claim/refund) against the running devnet.

The Python harness below is legacy: `make demo` now runs the Rust client journey, and
`make legacy-demo` still runs the Python scenarios for one release.

## Quickstart (legacy harness)

Prerequisites: Docker, Python 3.12, and rchain-rust at `../RNodeRust` (override `RCHAIN_RUST_DIR`).

```sh
make venv                 # .venv + harness deps
make image                # build rnode:local (once; slow)
make devnet               # one-validator autopropose devnet
make keys                 # generate/fund devnet keys
make probes               # phase-0 capability gates
make bootstrap            # Directory, Accounts, Oracle, rNGN/rKES zones, Components
make pool                 # pool setup + FxPool deploy
make book                 # TransferBook deploy
make legacy-demo          # the original Python pool + transfer scenarios
make down                 # stop and drop the devnet
```

`make demo` is the end-to-end Rust client story: refresh the oracle, fund an Account, open
NGN/KES vaults, borrow local stablecoins, add and remove liquidity, convert, send a
claimable transfer, claim it, refund an expired one, and read the balances back. It prints
PASS/FAIL per step and exits non-zero on the first failure.

## Architecture

- `Account` — non-custodial, per-key; purses for REV/rNGN/rKES/LP; vault and transfer ops.
- `CurrencyZone` (per currency) — local stablecoin kit, REV collateral, vaults, interest, liquidation.
- `FxPool` (per corridor) — oracle-anchored fixed-price market maker; LP tokens; spread + skew.
- `OracleHub` — allowlisted reporters, median, freshness, spread, 2-of-3 admin signatures.
- `TransferBook` — quote/send/claim/refund with escrowed destination currency and claim secrets.
- `Directory` + `ComponentRegistry` — names/assets and live large-contract channels.
- `Governor`-style admin — M-of-N secp256k1 signatures in every mutable component.

## Docs

[`docs/INTENT.md`](docs/INTENT.md) — why, users, principles, scope and success criteria.
[`docs/SPEC.md`](docs/SPEC.md) — the normative v0.1 specification: states, operations, invariants,
formulas, conformance.
[`docs/NETWORK.md`](docs/NETWORK.md) (corridors), [`docs/PLATFORM.md`](docs/PLATFORM.md) (pinned
node, hard limits, measured costs), [`docs/STATUS.md`](docs/STATUS.md) (verdict + deferred work),
[`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md), [`docs/LEGAL.md`](docs/LEGAL.md).

## License

AGPL-3.0-only. Code committed through `d5d613b` was Apache-2.0; those grants are not
revoked. Third-party notices — including the pinned AGPL-3.0 node crates and the
Apache-2.0 RhoGov signer used as a parity reference — are in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
