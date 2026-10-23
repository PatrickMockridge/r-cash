# R-Cash core specification

This directory is the normative specification for the v0.3 contract core. It replaces the
monolithic v0.1/v0.2 contract descriptions in `docs/SPEC.md` for all new work.

Read in order:

1. [`00-CALCULUS.md`](00-CALCULUS.md) — components, state cells, capability provenance,
   composition protocols and the laws an implementation must preserve.
2. [`10-COMPONENTS.md`](10-COMPONENTS.md) — the component catalogue and the split of each
   current monolith.
3. [`20-INVARIANTS.md`](20-INVARIANTS.md) — every invariant, its single owner, its
   enforcement point and its test obligation.
4. [`30-WIRING.md`](30-WIRING.md) — bootstrap order, `Root`, factories and directories,
   activation, rotation and freeze.

The machine-readable catalogue is [`contracts/components.json`](../../contracts/components.json).
The TLA+ models are in [`spec/tla`](../../spec/tla).

The specification is deliberately conservative: every state cell has one owner, every
capability has a provenance, every canonical field has an on-chain check, and every
cross-component operation uses one of the composition protocols. A design that violates a
law is a defect, not an optimisation.

Checks:

```sh
python3 tools/measure_contracts.py --check
python3 tools/check_arch.py --check
python3 tools/check_captures.py --check
make tla-check                 # optional; requires TLC on PATH
```

The TLA+ files are specifications, not runtime dependencies. TLC is a Java tool, so it is
not part of the required build; the finite models are committed so they can be checked on a
workstation or in a separate job.
