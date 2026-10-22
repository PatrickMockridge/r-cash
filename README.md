# R-Cash

A permissionless multi-currency account and cross-border payments network on
[rchain-rust](https://github.com/rchain-community/rchain-rust).

R-Cash is the on-chain payments core of a Wise-shaped product: hold local-currency balances,
receive as if local, convert directly between currencies, pay anyone with a wallet or claim link,
and get paid — while liquidity providers earn the FX spread.

## What works today (devnet)

| Area | Result |
|---|---|
| Capability gates | 12/12: persistence, rollback of tuple space and native ERTP/REV, ERTP across blocks, deployerId containment, signatures, claim hashing |
| Accounts + Directory | 7/7: non-custodial per-key Account, owner-only withdrawal, two keys, locked Directory |
| Oracle | 19/19: signed reporters, median, freshness/spread, cross rate, 2-of-3 admin |
| CDP / local stablecoins | 19/19: rNGN and rKES, REV collateral, borrow/repay, MCR, interest, liquidation (17/17) |
| rNGN/rKES FxPool (FPMM) | 14/14: add/remove liquidity, LP tokens, swaps both ways, oracle spread + skew |
| Transfer/claim/refund | 7/7: send with a claim hash, claim with the secret, refund after expiry |

**Devnet only.** The node is pre-testnet (rchain-rust #242); no real funds, no fiat custody.

## Quickstart

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
make demo                 # pool + transfer scenarios (seeds the CDP and liquidity)
make down                 # stop and drop the devnet
```

`make demo` is the end-to-end story: fund an Account, open NGN/KES vaults, borrow local
stablecoins, add liquidity, swap, remove liquidity, send a claimable transfer, claim it, and refund
an expired one. It prints PASS/FAIL per assertion.

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

Apache-2.0.
