# Refusal decisions (R1)

Every refusal is a reply-position string literal in a v3 deploy. The inventory
(`tools/rho_inventory.py`) extracts them; `tools/check_flows.py` requires each
arm's YAML refusal set to equal the source set and requires each reason to be in
`docs/SPEC.md` §18.3. The catalogue is generated from the same inventory, so the
two cannot drift silently.

## Decision

| decision | count | meaning |
|---|---|---|
| canonical | 164 | the string is part of the public refusal interface and is listed in §18.3 |
| add-to-spec | 0 | none left; the catalogue was rewritten from the inventory |
| normalize-to | 0 | no renames in this pass; a rename changes the refusal interface and is a separate change |
| internal | 0 | every literal is returned to a caller (directly or through a helper's `ret`) |

No reason is internal: the helper refusals (`params hash`, `terms fields`,
`below threshold`, `feed attestation`, …) are returned unchanged by the arm's
`ret`, so they are observable and canonical.

## Deliberate distinctions kept

- `bad vault auth`, `bad custody authority`, `bad directory authority`,
  `bad index authority`, `bad liquidation authority`, `bad mint authority`,
  `bad burn authority`, `bad settlement authority`, `bad buffer authority`,
  `bad savings authority` name the capability that failed. Collapsing them
  would remove the operator's ability to tell a missing capability from a bad
  caller, so they stay distinct.
- `funded`, `unfunded`, `locked`, `closed` are the lock state machine.
  `closed` also covers a terminal transfer.
- `deposit`, `burn`, `payment`, `custody` are returned with the payment so the
  caller can recover value after a native effect refused.

## Deprecations

| reason | replacement | when |
|---|---|---|
| `height` (`LiquidityLock.fund`, `untilHeight <= 0`) | `lock too short` | with the L1 reconciliation; `height` remains canonical until the code changes |

`lock too short` is already emitted by `marketOwnerCheck` and
`boundsTermsSemantic`; L1 extends it to the lock arm itself.

## Source list

The canonical list is the fenced block in `docs/SPEC.md` §18.3. It is generated
from the inventory, sorted, and checked by `make check-flows`.
