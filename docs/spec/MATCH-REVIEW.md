# Match-Statement Effectiveness Review

Status: reviewed 2026-11-07. Gate: `python3 tools/check_match.py --check`.
Baseline: `tools/match_baseline.json`.

## 1. Scope and method

This review covers every `match` statement and every `for`/`contract` pattern binder in
`contracts/src/deploy/v3/` (19 files). It asks not whether `match` is used, but whether it
is used **effectively**: does each match express one decision, is every partial pattern
made total or deliberately baselined, and do the values being matched have the tagged
shape that makes matching worthwhile?

The evidence is a lexical scanner (`tools/check_match.py`) plus a manual reading of every
arm. The scanner is not a Rholang parser; it uses the brace matcher in
`tools/rho_inventory.py`, the same approach as `check_captures.py`. It fails closed:
`G-MATCH-00` reports any `match` token it cannot parse.

Before the rewrites the corpus had **330 matches and 598 arms**; after the totality and
receive work it has **371 matches**, because total arms and catch-all receives are now
explicit. The counts below are the post-review state.

## 2. Why a non-match is a liveness bug

Rholang patterns are structural. A lowercase identifier **binds**; it does not compare.
`match assetIn { base => ... }` binds the value to a new `base`, even if `base` is in
scope. Patterns have no guards, so numeric ranges stay `if`. Data-map patterns are not
available; fields are read with `.get`.

Both pattern positions are partial and silent:

- a `match` with no matching arm **evaluates to the empty process** (the RChain "Illegal
  Moves" note); the continuation simply does not run;
- a `for`/`contract` receive whose pattern does not match **leaves the message
  unconsumed**; the continuation never runs.

Neither is an error. That makes exhaustiveness a liveness obligation, not a type check:
WF2 (one reply), WF6 (responsive awaits) and L1 (committed consumed cell) in
`00-CALCULUS.md`, and SPEC-MOD-07/09 in `SPEC.md`. A success-only receive is the most
dangerous shape because the caller waits forever while the deploy can still commit.

## 3. Rubric

| ID | Criterion |
|---|---|
| E1 | one semantic decision per match; arms partition one scrutinee |
| E2 | every partial match is total or annotated with `// match-total: <reason>` |
| E3 | patterns capture the shape needed; no rebinding a whole value and re-projecting it |
| E4 | no chains of match-as-let; one binding is idiom, a chain is a helper or an expression |
| E5 | helpers return tagged `(true, Out)` / `(false, Reason)`, not bare booleans |
| E6 | receive patterns obey the same totality rule as match arms |
| E7 | no decision-after-effect without `1/0` rollback |

## 4. Quantified baseline (post-review)

| Measure | Value |
|---|---|
| files | 19 |
| `match` statements | 371 |
| arms | 751 |
| binding arms (`_`, variable, tuple-binding) | 377 (50%) |
| tagged-tuple arms | 244 |
| string-literal arms | 37 |
| `for` clauses / success-only clauses | 823 / 39 |
| receive statements with a success-only clause | 29 |
| single-binding "let" matches | 53 |
| gate findings | 62, all baselined |

Arm classes: wildcard 243, variable 122, tuple-tagged 244, literal 81, string 37,
tuple-binding 12, tuple-string 9, integer 3.

Depth against the four-level rule: 147 of 371 matches are within four levels and 224 are
deeper; the full histogram is in `check_match.py --report`. Depth is reported per file as
G-MATCH-09, not per site, because the refactor is a separate programme.

## 5. Findings

| ID | Finding | Severity | Status |
|---|---|---|---|
| MATCH-01 | if-chain tag dispatch instead of `match` (market transition, asset kind, stablecoin admin actions, pool direction) | Medium | **fixed** |
| MATCH-02 | match-as-let chains; `vaultUpdate` was six deep | Low | **fixed** for the six-deep chain; five two-deep chains baselined |
| MATCH-03 | unchecked `args.nth` arity in admin handlers | Medium | **fixed** (`args.length()` guards) |
| MATCH-04 | partial matches with no irrefutable arm | High | **fixed** (total arms or `match-total` annotations) |
| MATCH-05 | silent catch-alls returning `false` / `(0, false)` | High | **fixed** except one vault-price fallback |
| MATCH-06 | helper replies untagged (`marketTransition`, `poolActive`, `poolOpen`, `poolRate`) | High | **fixed**; `vaultPrice` left on its `(rate, fresh)` pair |
| MATCH-07 | success-only component receives | High where a cell is held | 31 single-clause sites **fixed**; 39 clauses / 29 statements baselined |
| MATCH-08 | stored `Nil` tombstone conflates absent/dropped | Medium | **fixed** (`{"dropped": true}`) |
| MATCH-09 | two dispatch styles in one file (`14_asset_resolver`) | Info | **fixed** |
| MATCH-10 | repeated `dir == "b2q"` test in one swap | Low | **fixed** as four local matches; a `sides` helper is backlog |
| MATCH-11 | catch-all forwarding relies on callers, with no protocol check | Medium | report-only; the forwarding sites are unchanged |
| MATCH-12 | `_`-arm placement and duplicates | Info | **fixed**; no dead arms remain |

## 6. What changed

### 6.1 Totality

- Every partial match now has an irrefutable arm. Constructed pairs that cannot fail carry
  a `// match-total:` annotation (the three `feedSlot` destructures, the `feedRead` shape)
  rather than dead code.
- `match check` in the installer gained `_ => fail`; `feedRead` and the slot matches gained
  explicit fallbacks.
- Admin handlers now check `args.length()` before `args.nth` and refuse `"action"`; the
  stablecoin parameter handler matches its map fields with `Nil` refusals.

### 6.2 Dispatch

- `marketTransition` is a single `match (from, to)` with five legal pairs and a fallback.
- `14_asset_resolver` uses `match assetId` and `match entry.get("kind")` throughout; the
  two styles in one file are gone.
- The three stablecoin admin handlers use `match action`, matching the governor/root/feed
  convention.
- The pool swap tests direction four times; each is now a local `match dir`, and the
  repeated-test design smell is recorded, not hidden.

### 6.3 Tagged results

`marketTransition`, `poolActive`, `poolOpen` and `poolRate` return
`(true, payload)` / `(false, reason)`. Callers match and forward. External replies are
unchanged except where the old code collapsed distinct failures into `"not active"`; those
now forward the underlying reason (for example `no market`). The silent fallbacks in
`poolActive`, `poolOpen` and `poolRate` are gone.

`vaultPrice` deliberately keeps its `(rate, fresh)` pair. Converting it would touch eight
call sites and the vault/PSM flow taxonomy; the tail fallback is the single baselined
G-MATCH-06 finding (MATCH-05), and the conversion is tracked as a follow-up.

### 6.4 Receives

31 single-clause component-resolution receives became:

```rho
for (@r <- ch) {
  match r {
    (true, uri, _) => { <existing body> }
    (false, _why) => { ret!(1 / 0) }
    _ => { ret!(1 / 0) }
  }
}
```

The failure arm fails the deploy: a missing Root/ERTP component is a deployment error, not
a normal refusal, and `1/0` rolls back. Joins with several success-only clauses and the
installer continuations are baselined; converting them safely needs a devnet parse smoke
test because the rewrite adds a match layer and can exceed the four-level rule.

### 6.5 State

`dropReserve` stores `{"dropped": true}` instead of `Nil`; `reserveSend` treats a dropped
entry as absent and overwrites it. A dropped opId remains re-usable, the old unreachable
`Nil` write/read pair is gone, and absence is no longer conflated with a stored value.

## 7. Exemplars

- `09_identity.rho` `sendCommit`: all native success shapes (`Nil`, `true`, `(true, _)`)
  then `_ => 1/0`. This is the reference for an irregular native API.
- `09_identity.rho` `sendTransfer`: four-shape TransferBook reply, ending in `1/0`.
- `50_market.rho` `MarketDirectory.bind/seal`: tagged results, no bare booleans.
- `51_pool.rho` `poolOpen`: status dispatch with a total `_` arm.
- `04_governor.rho` admin dispatch: `match action` with an `"unknown admin action"` arm.

## 8. Deliberately not changed

- Numeric comparisons (`rate <= 0`, `rev` mismatch, bounds) stay `if`; patterns have no
  guards.
- Boolean OR predicates (`status == "active" || status == "paused"`) stay `if` for now.
  The match form is the union pattern `"active" \/ "paused"`, which cannot bind variables
  and is unused in the corpus; adopt it only after a devnet smoke test.
- Recursive list scans stay recursive; a pattern cannot compare against a variable key.
- `contract F(@"method", ...)` literal parameters are a co-designed method protocol, not a
  partial match; they are out of scope.
- The five internal boolean predicates (`adminAnySig`, `CollateralMath@"health"`,
  `omIsFresh`, `omDecide`, `regInList`) stay boolean. They are internal predicates whose
  callers are one line away; tagging them adds no safety.
- Five two-deep let-chains remain: the `args.nth` destructures and the purse/brand reads.
  Two-deep binding is Rholang's `let`; only the six-deep chain was a defect.

## 9. Remaining baseline

| Rule | Count | Reason |
|---|---|---|
| G-MATCH-05 | 39 | component-resolution receives in nested installer/join positions; converting them needs a devnet syntax smoke test and depth review |
| G-MATCH-06 | 1 | `vaultPrice` `(0, false)` fallback; shape conversion deferred with eight call sites |
| G-MATCH-08 | 5 | reviewed two-deep let-chains (args arity checks now precede them) |
| G-MATCH-09 | 12 | per-file aggregates above the four-level rule; refactor backlog |
| G-MATCH-11 | 5 | internal boolean predicates, accepted |

Every baseline key names the file, line, rule and detail; `--strict` remains an
aspirational local run. CI uses `--check`, so new debt fails the build.

## 10. Verification

```sh
python3 tools/check_match.py --report
python3 tools/check_match.py --check
make match-check
make spec-check formal-check
```

What cannot be verified offline: the Rholang parse of any new pattern form and the actual
message-consumption behaviour of the converted receives. The review therefore uses only
forms already present in the corpus; the remaining list/union-pattern ideas are backlog
items with a devnet parse smoke test as the adoption trigger.
