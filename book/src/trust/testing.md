# Testing and the acceptance campaign

R-Cash has three test layers: static gates that never touch a chain, offline model and client
tests, and behavioural suites that run against a disposable devnet or testnet. Each layer
answers a different question, and none of them substitutes for an audit.

## Static gates

These run in CI and on a workstation without Docker:

| Gate | Command | What it checks |
|---|---|---|
| Language policy | `make check-languages` | Only Rust, Rholang, Python, TypeScript; no native code |
| Build | `make build` | Assembles the deploy terms from the sources |
| Measure | `make measure-check` | Byte and parser-depth budgets |
| Architecture | `make check-arch` | Component boundaries and catalogue |
| Captures | `make check-captures` | No capability in a reply, map, bundle or attestation |
| Flows | `make check-flows` | Arm coverage, access, guards, refusals, tokens |
| Traceability | `make check-trace` | SPEC ↔ acceptance ↔ checks ↔ flows ↔ Lean |
| Mesh | `make check-mesh` | The tracked currency set, pairs and evidence |
| Vectors | `make vectors-check` | Market-term and arithmetic vectors |
| Lean | `make lean-check` | Build, no forbidden axioms, axiom audit |
| Rust | `cargo fmt --check`, `clippy -D warnings`, `cargo test` | Client and chain code |
| WASM | `cargo check --target wasm32-unknown-unknown`, wasm tests | Browser build |
| Web | `npm run typecheck`, `npm test`, `npm run build` | React app |

`make spec-check` chains build, measure, architecture and captures. `make formal-check` chains
Lean, flows, traceability and mesh. `make pre-devnet-check` runs the full static set plus the
Rust, WASM and web gates.

A static gate is fast and deterministic. It does not prove behaviour on chain.

## Offline tests

The offline layer includes:

- the Python model in `tests/model/`, an independent executable model of the transitions and
  the mesh;
- the market-term vectors in `tests/terms/` and `tests/vectors/`;
- the Rust workspace tests, including the deploy encoding and signature parity;
- the WASM host tests and the Node smoke test;
- the web unit tests.

The Python model is an **independent test model**, not the authority. Lean and the flow spec
win on disagreement; the model is useful because it can be executed and falsified quickly.

## The behavioural suites

The `harness/unit_*.py` files exercise a concept against a running devnet. The suite family
covers:

| Suite | Concept |
|---|---|
| `unit_v3` | Kernel, Root, install and basic authority |
| `unit_feed` | Reporter submissions, median, freshness, spread |
| `unit_hub` | Cross-rates and per-feed ages |
| `unit_stablecoin` | Issuer creation, listing, mint and views |
| `unit_interest` | Accrual, repay split, totals |
| `unit_liquidation` | Health, close factor, seizure, write-off, buffer |
| `unit_savings` | Shares, yield notification, position |
| `unit_psm` | Buy/sell, fees, signed debt, ceiling, buffer |
| `unit_timelock` | Schedule, early execute, apply, nonce |
| `unit_accounts` | Account creation, purses, deposits, history |
| `unit_transfer` | Send, claim, refund, expiry, exclusivity |
| `unit_transfer_memo` | Memo, opId, stipend, bounds |
| `unit_market` | Terms, factory, seed, lock, activation, swap, exit |
| `unit_mesh` | Reverse lookup, guard order, `pauseAsset` |
| `unit_external` | External asset registration and filtering |

`unit-buffer` and `unit-pool` are aliases that name the specification areas; the checks live
in the liquidation and market suites.

Run one suite:

```sh
make unit-stablecoin
```

Run the ordered campaign list:

```sh
make unit-all
```

Each suite assumes a running devnet with the components installed and the demo systems
bootstrapped. The [quickstart](../guides/quickstart.md) and
[operations](../guides/operations.md) chapters cover the setup.

## The campaign record

The committed devnet campaign is in
[`docs/spec/flows/CAMPAIGN.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/flows/CAMPAIGN.md).
It records:

- the fixed rholo node and one-validator devnet;
- one install with no contract changes afterwards;
- one pass per suite, in order, on the same chain;
- 13 suites plus the CLI demo passing on 2026-10-27;
- the defects reconciled before the campaign.

The 13-suite campaign predates the mesh and external-asset suites. Those suites were added
afterwards and have their own evidence; they are not part of the recorded 13-suite result.

The public-testnet campaign is separate. Its 2026-10-28 run was **BLOCKED** by the operator's
resource-admission throttle, not by a contract result. The testnet was rebuilt on 2026-10-29,
and a full campaign has not been re-run. The [testnet chapter](../guides/testnet.md) records
the details.

## Evidence kinds

`docs/spec/checks.yaml` maps each check to one of four kinds:

| Kind | Example | What it means |
|---|---|---|
| `static` | `static:flows`, `static:lean` | The text and models are consistent |
| `offline` | `offline:model:vault`, `model:mesh` | A pure model or vector test passes |
| `campaign` | `campaign:unit-stablecoin` | A behavioural suite passes on a disposable chain |
| `platform` | `platform:atomicity` | A native rholo/ERTP assumption holds |

A requirement can have more than one check. A requirement with no check is a spec defect;
`check_traceability.py` fails it.

## What CI runs

`.github/workflows/ci.yml` has jobs for:

- language policy;
- formal checks (inventory, flows, render, traceability, mesh, vectors, model tests, Lean);
- Rust format, clippy and tests;
- WASM check and host tests;
- web typecheck, unit tests and build.

The browser journey is a manual workflow because it needs a running devnet. The behavioural
suites are not in CI; they need Docker and a node image.

## How to read a result

- **Static green** means the spec, the model and the harness agree. It does not mean the
  contract is correct on chain.
- **Offline green** means the pure model and the clients pass their tests. It does not mean
  the node accepts the deploy.
- **Campaign green** means the suite passed on a disposable chain with a pinned node. It is
  the strongest evidence in the repository, but it is not an audit and not a public network.
- **Platform green** means the native assumption was measured. It is evidence about the
  platform, not the app.
- **Blocked** is never a pass. A blocked stage is reported as BLOCKED with the upstream
  blocker.

## Reproducing the static gates

```sh
make venv
make spec-check
make formal-check
make check-languages
cargo test --workspace --exclude rcash-wasm
cargo check -p rcash-wasm --target wasm32-unknown-unknown
npm --prefix web run typecheck
npm --prefix web test
```

The formal checks need Python 3.12 with `pyyaml` and `hypothesis`, and Lean 4 for
`make lean-check`. TLC is optional.

> **Where to go deeper.** The flow method is in
> [`docs/spec/flows/README.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/flows/README.md);
> the evidence registry is
> [`docs/spec/checks.yaml`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/checks.yaml).
> The formal models are described in [How the protocol is verified](verification.md).
