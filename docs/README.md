# R-Cash documentation

Read in this order:

1. [`INTENT.md`](INTENT.md) — the problem, the product, users, principles, v0.1 scope, success
   criteria and the trust boundaries.
2. [`SPEC.md`](SPEC.md) — the normative v0.1 specification: system model, authority, component
   topology, contract states and operations, invariants, economic formulas, governance, conformance
   evidence and planned work.
3. [`NETWORK.md`](NETWORK.md) — currencies, corridors and how a corridor is added.
4. [`PLATFORM.md`](PLATFORM.md) — the pinned rchain-rust node, hard platform limits, measured costs,
   finality and the build constraints the contracts are shaped by.
5. [`THREAT_MODEL.md`](THREAT_MODEL.md) — assets, adversaries, mitigations and residual risks.
6. [`STATUS.md`](STATUS.md) — what is implemented, measured, and deferred.
7. [`LEGAL.md`](LEGAL.md) — regulatory and compliance boundaries (not legal advice).

The reference implementation is `contracts/src/` (Rholang), `contracts/deploy/` (install terms),
`harness/` (devnet client and scenarios) and `spikes/` (phase-0 capability evidence).
