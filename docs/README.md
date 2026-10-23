# R-Cash documentation

Read in this order:

1. [`INTENT.md`](INTENT.md) — the problem, the product, users, principles, v0.1 scope, success
   criteria and the trust boundaries.
2. [`spec/README.md`](spec/README.md) — the normative v0.3 core specification: the component
   calculus, the composable component catalogue, invariant ownership and wiring. New contract
   work follows this specification; `SPEC.md` remains the v0.1 reference.
3. [`SPEC.md`](SPEC.md) — the v0.1 specification: system model, authority, component
   topology, contract states and operations, invariants, economic formulas, governance,
   conformance evidence and planned work.
4. [`NETWORK.md`](NETWORK.md) — currencies, corridors and how a corridor is added.
5. [`PLATFORM.md`](PLATFORM.md) — the pinned rchain-rust node, hard platform limits, measured costs,
   finality and the build constraints the contracts are shaped by.
6. [`CLIENT.md`](CLIENT.md) — the Rust SDK and CLI: signing, term encoding, node API, reads vs
   writes, failure taxonomy and the parity gates.
7. [`FRONTEND.md`](FRONTEND.md) — the React app, wallet and keystore, claim links, and why
   freshness-gated reads are signed.
8. [`LANGUAGES.md`](LANGUAGES.md) — the language policy: Rust, Rholang, Python and
   TypeScript, plus TLA+ specifications.
9. [`THREAT_MODEL.md`](THREAT_MODEL.md) — assets, adversaries, mitigations and residual risks.
10. [`STATUS.md`](STATUS.md) — what is implemented, measured, and deferred.
11. [`LEGAL.md`](LEGAL.md) — regulatory and compliance boundaries (not legal advice).
12. [`SPIKE-METAMASK.md`](SPIKE-METAMASK.md) — the MetaMask signing experiment: method and
    go/no-go criteria; not run.

The protocol reference implementation is `contracts/src/` (Rholang) and `contracts/deploy/`
(install terms). The client reference is `crates/` (Rust) and `web/` (React + WASM).
`harness/` and `tools/` remain as the legacy Python devnet harness and build tooling;
`spikes/` holds the phase-0 capability evidence.
