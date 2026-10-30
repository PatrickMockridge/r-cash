# R-Cash core specification

This directory is the normative formal core for the v0.5 contracts. It is used with
[`docs/SPEC.md`](../SPEC.md), the product specification:

- `docs/SPEC.md` wins for product behaviour and client requirements.
- `docs/spec/00-30` win for the component calculus, invariants and install order.
- A statement in one that contradicts the other is a defect in one of them and must be
  resolved before implementation.

The human-readable explanation is in [`book/`](../../book/src/index.md). The book links to
this directory; it does not duplicate it.

Read in order:

1. [`00-CALCULUS.md`](00-CALCULUS.md) — components, state cells, capability provenance,
   composition protocols and the laws an implementation must preserve.
2. [`10-COMPONENTS.md`](10-COMPONENTS.md) — the component catalogue and the split of each
   current monolith.
3. [`20-INVARIANTS.md`](20-INVARIANTS.md) — every invariant, its single owner, its
   enforcement point and its test obligation. This is the sole normative invariant text.
4. [`30-WIRING.md`](30-WIRING.md) — bootstrap order, `Root`, factories and directories,
   activation, rotation and freeze.

Supporting material:

- [`EXTERNAL-ASSETS.md`](EXTERNAL-ASSETS.md) — the adapter interface for bridged assets.
- [`flows/README.md`](flows/README.md) — the behavioural transition specification.
- [`acceptance.yaml`](acceptance.yaml) — requirement → acceptance criteria.
- [`checks.yaml`](checks.yaml) — the evidence registry.
- [`model.yaml`](model.yaml) — transition → model test and vectors.

The machine-readable catalogue is [`contracts/components.json`](../../contracts/components.json).
The TLA+ models are in [`spec/tla`](../../spec/tla). The Lean models are in
[`spec/lean`](../../spec/lean).

The specification is deliberately conservative: every state cell has one owner, every
capability has a provenance, every canonical field has an on-chain check, and every
cross-component operation uses one of the composition protocols. A design that violates a
law is a defect, not an optimisation.

Checks:

```sh
python3 tools/measure_contracts.py --check
python3 tools/check_arch.py --check
python3 tools/check_captures.py --check
make formal-check
make tla-check                 # optional; requires TLC on PATH
```

The TLA+ files are specifications, not runtime dependencies. TLC is a Java tool, so it is
not part of the required build; the finite models are committed so they can be checked on a
workstation or in a separate job.
