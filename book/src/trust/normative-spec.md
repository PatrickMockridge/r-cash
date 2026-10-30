# The normative specification

This book explains. It does not govern. The normative sources are `docs/SPEC.md` for product
behaviour and `docs/spec/` for the formal core. This chapter explains how to read them and how
a change flows through the repository.

## The authority order

1. **Contracts and the formal core** — `contracts/src/`, `docs/spec/00-CALCULUS.md`,
   `10-COMPONENTS.md`, `20-INVARIANTS.md`, `30-WIRING.md`, and the flow YAML plus Lean models.
2. **Product behaviour** — `docs/SPEC.md`. It wins for product behaviour and client
   requirements. A contradiction with the formal core is a defect in one of them.
3. **Evidence** — `docs/spec/acceptance.yaml`, `checks.yaml`, `model.yaml` and the harness.
4. **Explanation** — this book. If the book and a normative source disagree, the normative
   source wins and the book must be fixed.

The [repository map](repository-map.md) lists where each layer lives.

## How to read SPEC.md

`docs/SPEC.md` is a product specification written in RFC 2119 language: MUST, MUST NOT,
SHOULD, MAY. It has 20 sections. The first two are the key to the rest:

- **§1 Document control** defines the requirement id format `SPEC-<AREA>-NN`, the acceptance
  criterion format `AC-SPEC-<AREA>-NN.k`, and the status vocabulary.
- **§2 Scope, actors and units** defines the actors, the 8-decimal unit and the scope.

Every requirement row has:

| Column | Meaning |
|---|---|
| ID | `SPEC-<AREA>-NN` |
| Level | MUST, SHOULD or MAY |
| Requirement | The normative statement, often with the exact refusal |
| Owner | The component or surface responsible |
| Status | `implemented`, `planned`, `blocked` or `excluded` |

Statuses are not a quality score:

- `implemented` — the code exists and exhibits the behaviour; campaign evidence may be
  pending.
- `planned` — specified but not implemented, or implemented but not wired.
- `blocked` — cannot complete without an upstream change; the blocker is named.
- `excluded` — out of scope, listed in §19.

A requirement is conformant only when every acceptance criterion passes in the final campaign.
An `implemented` row is not a pass.

## Acceptance criteria

Every criterion is a state transition or a command:

```
AC-SPEC-<AREA>-NN.k
Given <initial state>
When <actor action>
Then <exact reply or exact state delta>
```

Refusal strings are part of the interface. A test asserts the exact string, not a substring or
a paraphrase. The canonical list is §18.3; it is generated from the deploy inventory and
checked against the flow transitions.

The acceptance file `docs/spec/acceptance.yaml` is a machine-readable mirror. It was generated
once as a skeleton and is now reviewed by hand. It is not a second source of truth: a change to
SPEC.md must be reflected there, and `check_traceability.py` enforces the mapping.

## The status vocabulary in evidence

`checks.yaml` uses `static`, `offline`, `campaign` and `platform`. The campaign report uses
PASS, FAIL, BLOCKED and SKIPPED. BLOCKED is never reported as conformance.

A green static gate means the specification and the model agree. A green campaign means a
suite passed on a disposable chain. Neither is an audit. The [testing chapter](testing.md)
explains what each layer proves.

## The flow specification

The behavioural authority is `docs/spec/flows/`. Each subsystem has a YAML transition table.
The Markdown files in the same directory are generated; do not edit them.

A flow entry records the arm, the transition, the Lean name, the source location, the guards
(with refusal, phase, repost and fail behaviour), the effects, the access pattern, the nested
calls, the refusals and the invariants. The `status` is `unreconciled`, `fixed`, `verified` or
`blocked`. Strict mode accepts only `verified`, or `blocked` with a named blocker.

The source of truth for the arm list is `contracts/build/arm_inventory.json`, produced by
`tools/rho_inventory.py` from the deploy sources. A hand list would drift; the inventory is
generated.

## Changing the spec

A behaviour change is not a docs edit. The flow is:

1. **Decide the transition.** What state changes, what guards apply, what refusal is returned?
2. **Update the contract** in `contracts/src/`.
3. **Update the flow YAML** with the arm, guards, effects, access, refusal and invariants.
4. **Update the Lean model** if the transition or an invariant obligation changes.
5. **Update SPEC.md** if the product behaviour or a requirement changes.
6. **Update acceptance.yaml** with the criteria and checks.
7. **Update the harness/model tests** and the vectors if needed.
8. **Regenerate** the arm inventory and the flow docs.
9. **Run** `make formal-check` and `make spec-check`.
10. **Update this book** if the explanation or a status claim changes.

If the book contradicts the spec, fix the book. If the spec contradicts the formal core, fix
whichever is wrong and record the decision.

## What the book must not do

- It must not restate requirement tables, acceptance criteria or the full refusal list. It
  links to them.
- It must not present a planned or blocked item as done.
- It must not invent a parameter, a campaign result or an address.
- It must not describe a mechanism differently from the flow YAML and the Lean model.
- It must not become a second source of truth.

The last rule is the important one. A book that duplicates the spec will drift. A book that
explains and links can stay correct.

## Where the files are

| File | Role |
|---|---|
| `docs/SPEC.md` | Product specification, 20 sections |
| `docs/spec/00-CALCULUS.md` | Component calculus, laws, composition protocols |
| `docs/spec/10-COMPONENTS.md` | Component catalogue and split |
| `docs/spec/20-INVARIANTS.md` | Sole normative invariant text |
| `docs/spec/30-WIRING.md` | Bootstrap, factories, directories, lifecycle |
| `docs/spec/acceptance.yaml` | Requirement → acceptance criteria |
| `docs/spec/checks.yaml` | Evidence registry |
| `docs/spec/model.yaml` | Transition → model test and vectors |
| `docs/spec/flows/*.yaml` | Behavioural transitions |
| `docs/spec/flows/*.md` | Generated diagrams and tables |
| `contracts/components.json` | Machine-readable component catalogue |

> **Where to go deeper.** Start with
> [`docs/SPEC.md` §1](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#1-document-control)
> and
> [`docs/spec/README.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/README.md).
> The flow method is in
> [`docs/spec/flows/README.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/flows/README.md).
