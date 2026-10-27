# Flow specification

This directory is the behavioural authority for the contracts. Each subsystem has a
YAML transition table; the Markdown state diagrams and tables are generated from it.
`docs/SPEC.md` remains the product layer and `docs/spec/00-30` the calculus; where this
directory and the prose disagree, this directory plus the Lean model govern.

## 1. What a transition is

A transition is the **net state change of one deploy path**, including nested pinned
calls. A nested call is not automatically a transition.

- `Stablecoin.mint`, `Stablecoin.burn`, `Stablecoin.settle` and `cover(b>0)` are
  internal effects of an issuer transition.
- `cover(0)` is an independently S3-preserving transition (it reconciles `sin`).
- `VaultBook.mint/deposit/withdraw/repay/liquidate`, the write-off, PSM buy/sell and the
  account/transfer/registry/market/pool arms are the atomic transitions.

An invariant is attached to the atomic transition that can preserve it, never to every
arm that happens to touch a cell.

## 2. The linear cell discipline

State is a linear store `CellId → List α`:

```
peek c     requires s c = v :: rest; leaves s unchanged
take c     requires s c = [v]; sets s c = []; adds c to held
put c v    requires s c = [] and c ∈ held; sets s c = [v]; removes c from held
call A     requires A ∩ held = ∅; leaves the store unchanged
```

A trace is well formed (`WF`) when it finishes with `held = []`.

| Defect | Shape | Rejected because |
|---|---|---|
| D1 duplicate cell | `peek c; put c v` | `put` requires `c ∈ held` |
| D2 lost cell | `take c; refusal` with no `put` | final `held` is non-empty |
| D3 nested take | nested `call` touching a held cell | `call` requires disjoint access |
| D4 lost update | `peek c; ...; put c v'` without a take | `put` requires a take |
| D5 duplicate binder | outer `new x` shadowed before use | reported by the inventory |
| D6 sort confusion | value used as a name or vice versa | reported by the source scan |

A refusal after a `take` must either `put` the unchanged cell (`reposts: true`) or fail
the deploy (`fail: true`, `1/0`), which rolls the take back. A graceful refusal with
neither is a D2 defect.

## 3. Protocol labels

| Label | Meaning |
|---|---|
| P0 | pure helper, no cell access |
| P1 | single-cell commit |
| P2 | await-then-commit |
| P3 | effect-then-commit |
| P4 | hold-through-native (ERTP/REV) |
| P5 | reserve/confirm |
| P6 | fail-closed |

Helper classes:

| Class | Rule |
|---|---|
| H1 | pure transformer: receives state by value, returns the new state, the caller posts. |
| H2a | caller-token: the caller took the cell; the helper receives the state value and posts exactly once; the caller does not post on that path. |
| H2b | delegated critical section: the helper takes and posts the cell; the caller only peeks. |

`stageMarket`, `stagePairCheck` and `commitLiquidity` are H2a. `vaultMintCommit`,
`repayCommit`, `vaultLiquidateCommit` and `vaultWriteOff` are H2b.

## 4. YAML schema

```yaml
schema: rcash.flows/v1
subsystem: vault
source_globs: [contracts/src/deploy/v3/31_stablecoin.rho]
invariants:
  S3: {statement: "...", lean: Rholphin.Invariants.S3}
components:
  - name: VaultBook
    state_cell: vaultState
    lean_module: Rholphin.Model.Vault
    arms:
      - arm: 'VaultBook@"mint"'
        transition: vault.mint
        lean: Rholphin.Model.Vault.mint
        kind: mutate
        source: {file: contracts/src/deploy/v3/31_stablecoin.rho, line: 1039}
        guards: [{id: buffer_halt, expr: "not (sin > surplus)",
                  refusal: {reason: recapitalise, phase: after_consume,
                            reposts: true, fail: false}}]
        effects: [{target: totalDebt, formula: "totalDebt + (accrued - v.debt) + amount"}]
        access:
          - {cell: vaultState, mode: peek, actor: arm, phase: pre}
          - {cell: vaultState, mode: consume, actor: 'helper:vaultMintCommit', phase: commit}
          - {cell: vaultState, mode: post, actor: 'helper:vaultMintCommit', phase: commit,
             on: [success, recapitalise]}
        nested_calls:
          - {callee: 'Stablecoin@"mint"', protocol: P4, internal: true}
          - {callee: vaultMintCommit, protocol: H2b, takes: [vaultState],
             puts: [vaultState], post_owner: helper}
        refusals:
          - {reason: recapitalise, phase: after_consume, reposts: true, fail: false}
        invariants: [S1, S2, S3, S4]
        status: unreconciled
```

Required fields: `arm`, `transition`, `lean`, `kind`, `source`, `access`, `refusals`,
`status`. Mutating arms also require `guards` and `effects`; arms with nested calls
require `nested_calls`.

`status` is `unreconciled`, `fixed`, `verified` or `blocked`. Strict mode accepts only
`verified`, or `blocked` with a named blocker; `blocked` is never conformance.

## 5. Generated files

`TRACEABILITY.md` and `RECONCILIATION.md` are generated. The source of truth for the arm
list is `contracts/build/arm_inventory.json`, produced by `tools/rho_inventory.py` from
the deploy sources with a brace-matching scope tree, never a hand list.

Commands:

```sh
make inventory     # regenerate the arm inventory
make flows         # regenerate the Mermaid diagrams and tables
make check-flows   # strict completeness, access, refusal and token checks
make formal-check  # Lean build + no-sorry/axiom audit + check-flows
```
