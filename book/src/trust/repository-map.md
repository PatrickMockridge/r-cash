# Repository and implementation map

This chapter is the map from a concept to the code that implements it. It is also the
language policy: R-Cash is Rust, Rholang, Python and TypeScript, with formal specifications
in Lean 4 and TLA+.

## Top level

| Path | What lives there |
|---|---|
| `contracts/` | Rholang contracts, deploy terms, component catalogue |
| `crates/` | Rust workspace: core, chain, SDK, CLI, WASM |
| `web/` | React + Vite + TypeScript client |
| `harness/` | Python devnet/testnet orchestration and behavioural suites |
| `tools/` | Build, verification, mesh and deployment tooling |
| `docs/SPEC.md` | Normative product specification |
| `docs/spec/` | Formal core, acceptance/checks, flows |
| `spec/lean/` | Lean 4 models and proofs |
| `spec/tla/` | TLA+ models |
| `configs/` | Mesh and testnet profiles |
| `deployments/` | Generated manifests |
| `book/` | This book |
| `tests/` | Model, parity, terms and vector fixtures |
| `spikes/` | Phase-0 capability evidence |

## Contracts

`contracts/src/` is the protocol reference implementation. The deploy terms are under
`contracts/src/deploy/`; the built terms under `contracts/build/`. The component catalogue is
`contracts/components.json` (40 components).

| Concept | Contract |
|---|---|
| Kernel, Root, Clock, Verifier, Codec, Bounds, AdminGuard | `contracts/src/deploy/v3/00_root.rho`, `01_kernel.rho`, `02_bounds.rho`, `04_governor.rho` |
| Oracle feed, registry, hub | `31_feed.rho`, `12/13` oracle modules |
| Stablecoin issuer cluster | `31_stablecoin.rho` |
| Currency registry and directory | `32_currency_registry.rho` |
| Asset resolver | `14` asset resolver module |
| Transfer book and per-transfer contract | `40_transfer.rho` |
| Market factory, directory, index, terms, gate, views | `50_market.rho` |
| Pool and lock | `51_pool.rho` |
| Accounts and purses | `09_identity.rho` |
| Install terms | `contracts/src/deploy/v3/` and `contracts/deploy/` |

The contracts use library includes with `@@INLINE:...@@` markers, assembled by
`tools/build_contracts.py`. The v3 deploy core does not inline stateful components; see
`docs/spec/`.

## Rust crates

| Crate | Responsibility |
|---|---|
| `rcash-core` | Amounts (1e8 base units), validated asset/currency/URI newtypes, Rholang quoting, the manifest. No I/O |
| `rcash-chain` | DeployData, secp256k1 signing, REV addresses, devnet key files, node HTTP client, deploy-status polling, hostlist discovery and node pools |
| `rcash-sdk` | Connected client, deploy lifecycle, typed reads and writes |
| `rcash-cli` | The `rcash` binary |
| `rcash-wasm` | wasm-bindgen facade for the browser wallet and operations |

The node crates are pinned by git revision in `Cargo.toml`. The signing path is the node's own
cryptography; the wire shape is re-declared locally and pinned by golden bytes and parity
tests.

## Web

`web/src/routes/` contains the screens. `web/src/lib/` contains the wallet store, network
profile, mesh matrix, preferences and IndexedDB journal. The WASM build is produced by
`web/scripts/build-wasm.mjs`; the manifest is synced by `scripts/sync-manifest.mjs`.

## Harness and tools

`harness/` is the Python orchestration layer:

| File | Purpose |
|---|---|
| `deploy.py`, `chainclient.py`, `netconfig.py` | Node access and deploy/read helpers |
| `install_v3.py`, `install_testnet.py` | Chain-aware installers |
| `testnet_*.py`, `ticker.py`, `feed_refresh.py` | Public-testnet campaign tooling |
| `mesh_support.py` | Mesh provisioning |
| `unit_*.py` | Behavioural suites |
| `rcash.py` | Probes and legacy commands |

`tools/` contains the build and verification tooling:

| Tool | Purpose |
|---|---|
| `build_contracts.py` | Assemble deploy terms |
| `rho_inventory.py` | Arm inventory from the source |
| `render_flows.py` | Generate flow Markdown and diagrams |
| `check_flows.py` | Strict flow completeness |
| `check_traceability.py` | SPEC ↔ acceptance ↔ checks ↔ flows ↔ Lean |
| `check_lean.py` | Lean build and axiom audit |
| `check_mesh.py` | Offline mesh falsifiability gate |
| `check_arch.py`, `check_captures.py`, `measure_contracts.py` | Architecture, captures, budgets |
| `check_languages.py` | Language policy |
| `mesh.py` | Plan, install and pair the mesh |
| `deploy.py` | Low-level deploy helper |

## Formal specs

`spec/lean/` is the Lean 4 project (`rholphin`). It has no Mathlib dependency. `spec/tla/`
holds the five TLA+ models. Neither is imported by the application; they are specifications,
not runtime dependencies.

## Configs and deployments

`configs/mesh.json` is the tracked currency set. `configs/mesh-testnet.json` is the
price-level variant for the public faucet. `configs/testnet.json` pins the testnet identity,
endpoints, faucet, phlo and timeouts.

`deployments/devnet-v4.json` is the generated component manifest. Systems and markets are
discovered through `ListingViews`, not the manifest. Testnet manifests live under `.testnet/`
and are gitignored.

## Languages and the policy

| Layer | Language | Path |
|---|---|---|
| Protocol | Rholang | `contracts/` |
| Clients | Rust | `crates/` |
| Frontend | TypeScript + React | `web/` |
| Tooling, harness | Python | `tools/`, `harness/` |
| Concurrency specs | TLA+ | `spec/tla/` |
| Proofs | Lean 4 | `spec/lean/` |

`tools/check_languages.py` rejects native sources, native-compiling crates, native build tools
and native artifacts. The project is deliberately interpreted/WASM at the edges and Rholang
on chain.

## Platform limits that shape the code

These are measured, not assumptions:

- **Deploy term size: 65,536 bytes.** Larger terms are refused before parsing. The bootstrap
  is minified to fit; `tools/minify_rho.py` is string-aware.
- **Parser depth: 128.** Deeply nested terms fail. The shallow pool factory and the split
  deploys are a response.
- **Bundle free-variable check.** A bundle that captures a nested contract parameter is
  refused. Components are held in `Root` and resolved, not bundled.
- **BigInt intermediates are not normalized.** Use `.toInt()` at the fixed-point boundary; it
  fails closed if the value does not fit.
- **Name/value quoting.** A name bound by a receive used as a send argument needs `*x`; a
  value bound by `@x` is passed bare. Mixing them is a parse error.
- **A failed deploy reverts tuple space and native ERTP/REV state.**
- **An unmatched `for` is silent.** Every arm must reply or be deliberately fire-and-forget.
- **The devnet shard is `/root`**, not `root`.
- **`validAfterBlockNumber` anchors a 50-block lifespan.** A deploy anchored at 0 is never
  proposed.
- **`explore-deploy` has no block context.** Freshness-gated reads must be signed deploys.

Measured phase-0 costs, for budget intuition rather than protocol rules:

| Operation | Phlo |
|---|---|
| Counter install (small probe) | 2,777 |
| Counter call | 2,946 |
| Block data probe | ~1,000 |

Larger deploys (bootstrap, pool, transfer book) have budgets, not measured actuals. The
block's `deploys[].cost` is the authority when a campaign records them.

## Where to start

- To understand the product: [What is R-Cash?](../orientation/what-is-rcash.md).
- To understand the code: [Architecture at a glance](../concepts/architecture.md).
- To change behaviour: [The normative specification](normative-spec.md) and
  [`AGENTS.md`](https://github.com/PatrickMockridge/r-cash/blob/main/AGENTS.md).
- To run it: [Quickstart on the devnet](../guides/quickstart.md).

> **Where to go deeper.** The component catalogue is `contracts/components.json`; the language
> policy is enforced by `tools/check_languages.py`; the install order is in
> [`docs/spec/30-WIRING.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/30-WIRING.md).
