# HAZOP — smart-contract primitives

**Status:** Phase 1 register, static review. **Date:** 2026-11-04.

This is the primitive-level complement to [`HAZOP.md`](HAZOP.md). `HAZOP.md` classifies
shared channels and walks the client/hostlist path; this document applies the guide words to
the **recurring implementation primitives** and turns every deviation into one of:

- a **Lean obligation** (a law or preservation theorem whose proof rules the deviation out);
- a **Rholang fix** (R1–R6 in the improvement plan);
- a **gate** (a mechanical check that rejects the shape in future);
- an **accepted risk** with a rationale.

A deviation with none of these is itself a finding. The register is the input to the Lean
programme in [`AUDIT-PRIMITIVES.md`](AUDIT-PRIMITIVES.md) §6.

---

## 1. Method

**Nodes** are the primitive lifecycle:

```
acquire → validate → effect → commit → reply/refuse → release
```

**Parameters:** authority, value, state version, ordering, timing, capacity, configuration,
data size.

**Guide words:** No/Not, More, Less, As well as, Part of, Reverse, Other than, Early, Late,
Before, After.

**Normative shapes** (from [`00-CALCULUS.md`](00-CALCULUS.md) §7 and `20-INVARIANTS.md`):

| Primitive | Normative shape |
|---|---|
| P-cell | peek or take; every branch posts exactly one next state or fails |
| Cap | authority held only in a closure; caller names are sink-only |
| G | graceful refusal before effect; `1/0` after effect |
| P1 | take → validate → post, no await between |
| P2 | peek → external awaits → take → revalidate → post |
| P3 | peek → read/math → effect → take → revalidate `rev` → post |
| P4 | hold only across a native ERTP step |
| REV | monotone `rev`; bump on every mutation; compare after take |
| DIR | reads peek; writes take; bind is create-only/CAS |
| OPI | reserve → effect → finish; replay returns the stored result |
| ERTP | exhaustive reply match; fail after value movement |
| SIG | verify before any write; domain-separated preimage |
| H2 | direct token (H2a) or delegated token (H2b); caller caps never stored |

Each deviation below is recorded with the guide word that produced it. A guide word that was
examined and produced nothing is marked **none found** in the coverage matrix (§5); it is
not omitted.

---

## 2. Worksheet and deviation register

### 2.1 P-cell

| Guide word | Deviation / observation |
|---|---|
| No / Not | **PRIM-01** (proof gap): vault arms that detect a `rev` mismatch after a take fail without reposting. The deploy rolls back, so no cell is lost at runtime, but the cell law (D2) holds only under rollback semantics, which the model does not yet represent. |
| More | The same cell can be taken twice in one term if an arm is invoked twice; the second take blocks (correct), but the first must repost on every branch. |
| Part of | A branch may post only a subset of the fields; the model does not require a full next state. |
| Reverse | A post can restore a stale snapshot after a peek (D4). The flow checker catches the simple shape; the general shape is a Lean obligation. |
| Other than | Fail-without-repost is legal only because `1/0` rolls back; the source does not distinguish "rollback" from "lost cell". |
| After | A refusal after a take must repost or fail. The after-consume check is partial. |
| Early / Late / Before | The take must follow the last read used in the decision (P2/P3). |
| As well as | Multi-cell arms compose several P-cells; atomicity is not a P-cell property. |

### 2.2 Cap

| Guide word | Deviation / observation |
|---|---|
| As well as | **PRIM-13**: a caller-supplied name could be invoked on a non-sink arm; only a comment forbids it. |
| Other than | A sink facet and an authority are both names; no type distinguishes them. |
| Reverse | A delegated token (H2b) must be returned; provenance is checked only by `check_captures.py`. |
| Part of | An auth cap stored in a record instead of a closure would persist across a block; no model. |
| More | Capability duplication by the callee is not observable in the model. |

### 2.3 G — guard and refusal

| Guide word | Deviation / observation |
|---|---|
| Other than | **PRIM-02**: the same failure shape is graceful in `LiquidityLock.release/cancel` and `1/0` in transfer/pool. |
| Reverse | **PRIM-03**: a contention outcome is a generic `1/0`, indistinguishable from a bug. |
| Part of | **PRIM-18**: a graceful refusal after a write is not uniformly rejected. |
| Before / After | The rule is "graceful before effect, fail after"; the code does not apply it uniformly. |
| No / Not | A refusal string absent from §18.3 is not a protocol refusal; the checker only warns. |

### 2.4 P1 — single-cell commit

| Guide word | Deviation / observation |
|---|---|
| Part of | **PRIM-15**: pause + registry is two P1 commits with no joint version. |
| As well as | `createMarket` composes terms, directory, index and pool; the directory/index order is now guarded, but the composition is not one cell. |
| More | **PRIM-19**: the per-account op ledger grows without bound. |
| Reverse | A direct `VaultBook.pause` can reverse the registry relation. |

### 2.5 P2 — await-then-commit

| Guide word | Deviation / observation |
|---|---|
| Late | **PRIM-16**: a snapshot may be used after an external await without revalidation; the checker cannot see it. |
| Before | A take must follow the last external read; the declared `phase` is not compared to the source. |
| More | Multiple external reads widen the conflict window; harmless for correctness, relevant for phlo. |
| No / Not | A missing `rev` makes revalidation impossible. |

### 2.6 P3 — effect-then-commit

| Guide word | Deviation / observation |
|---|---|
| Before / After | **PRIM-04**: effect-before-take and take-before-effect are both used for the same purse-move + cell-write shape. |
| Other than | A pre-effect conflict can return a typed `"conflict"`; a post-effect conflict must fail. FxPool does the former; vault/PSM do the latter. |
| Late | A `rev` check after the effect is the correct guard; a missing `rev` defeats it. |
| More | The effect can be repeated if the deploy is retried without an opId. |

### 2.7 P4 — hold-through-native

| Guide word | Deviation / observation |
|---|---|
| More | None found: `LiquidityLock.fund/release/cancel` read the Clock and deployer identity before the take; the remaining holds are across native ERTP only. |
| Other than | None found after the transfer P3 fix: no arm holds a cell across a caller-supplied facet. |
| Late | **PRIM-20** (gate gap): nothing mechanically requires a post after the native reply is matched; no unsafe site was found. |
| No / Not | No post-native catch-all that returns a possibly-consumed name was found after the earlier sweep; G-NATIVE prevents regression. |

### 2.8 REV — version revalidation

| Guide word | Deviation / observation |
|---|---|
| No | **PRIM-06**: `oracleRegState` and `issuerState` have no `rev`. |
| Less | **PRIM-07**: a mutating arm can omit the bump; no gate. |
| Reverse | A stale snapshot can be posted after a concurrent branch changed the cell; `rev` is the guard. |
| Before | The `rev` must be read before the effect and compared after the take. |
| Other than | `rev` is a counter, not a content hash; equal `rev` does not prove equal content unless every writer bumps. |

### 2.9 DIR — directory and registry

| Guide word | Deviation / observation |
|---|---|
| Other than | **PRIM-14**: read-peek/write-take is not uniform; `oracleRegState` has no `rev`; `seal` has no `sealedBy`/terms-hash evidence. |
| Part of | A slot can be bound without being sealed, and sealed without a staged index entry (the latter is now guarded by the pre-check). |
| Reverse | A lower-version draft can be replaced by a higher version only after delisting; staging over a draft is constrained. |
| As well as | One registry write can mirror another component's status (pause). |
| No / Not | A directory read can return a draft; callers must check status. |

### 2.10 OPI — op-id idempotency

| Guide word | Deviation / observation |
|---|---|
| No | **PRIM-08**: `TransferBook.send` does not dedupe opId; a direct call creates a second transfer. |
| Late | **PRIM-09**: `sendCommit` ignores the `revVault!transfer` reply while the op commits. |
| Reverse | A replay must return the stored result, not re-execute. |
| More | **PRIM-19**: the ledger grows without bound. |
| Before | Reserve must precede the effect; finish must follow it. |
| Other than | The SDK cache and the on-chain ledger are two idempotency mechanisms; a caller can have one without the other. |

### 2.11 ERTP — native boundary

| Guide word | Deviation / observation |
|---|---|
| Other than | **PRIM-10**: a catch-all `_` after a native consume can return a possibly-consumed name. |
| No / Not | A missing reply match is a silent success (PRIM-09). |
| Early | **PRIM-20**: a post before the native reply is confirmed. |
| More | A payment can be moved twice if a retry is not idempotent. |
| Part of | A native failure branch that returns only the payment, not the reason, loses the audit trail. |

### 2.12 SIG — signature and quoting

| Guide word | Deviation / observation |
|---|---|
| No | **PRIM-11**: `MarketTerms.put` stores before any sponsor check. |
| Before | **PRIM-12**: the sponsor preimage has no domain, nonce or deadline, so a signature is not bound to a deployment. |
| Other than | `deployerId == sponsor` removes relayer submission but does not make the signature domain-separated. |
| As well as | The registry and feed preimages have different domains; only the market preimage lacks one. |
| Part of | Verification of the live attestation is separate from the signature check. |

### 2.13 H2 — capability hand-off

| Guide word | Deviation / observation |
|---|---|
| Other than | **PRIM-17**: caller-token provenance is asserted, not enforced; no Lean `Prov` model. |
| Reverse | A delegated token must be returned; nothing checks that it is. |
| As well as | A caller-supplied facet and a caller-supplied token are both names; the sink rule must distinguish them. |
| No / Not | A missing `check_captures.py` rule for a new arm is not caught by Lean. |

---

## 3. Deviation register (full records)

| ID | Prim. | Guide word | Deviation | Evidence | Severity | Disposition |
|---|---|---|---|---|---|---|
| PRIM-01 | P-cell | No / Not | a vault `rev` mismatch after a take fails without reposting; legal only under deploy rollback | `31_stablecoin.rho:362,419,1005,1144` | Medium | Lean `p3_fail_rolls_back`; G-AFTER |
| PRIM-02 | G | Other than | same failure shape graceful in one file, `1/0` in another; both locally safe | `51_pool.rho` vs `40_transfer.rho` | Medium | fix R1; Lean `p6`; G-AFTER |
| PRIM-03 | G | Reverse | contention reported as generic `1/0` | `31_stablecoin.rho:362,419,1005,1144` | Medium | pre-effect `"conflict"`; SDK classification; Lean `p3` |
| PRIM-04 | P3/P4 | Before/After | effect-before-take vs take-before-effect for one shape | `31_stablecoin.rho` savings vs buffer | Medium | fix R1; Lean `p3`/`p4` |
| PRIM-05 | P4 | More | **withdrawn**: `release/cancel` read Clock and identity before the take | `51_pool.rho:583-658` | Closed | none — the earlier draft was wrong |
| PRIM-06 | REV | No | `oracleRegState` had no `rev`; `issuerState` CAS is `totalPrincipal` | `12_oracle_registry.rho` | Medium | Fixed for oracle; document issuer CAS; G-REV |
| PRIM-07 | REV | Less | not every mutation bumps its version field | `31_stablecoin.rho`, `51_pool.rho` | Medium | G-REV; Lean `rev_monotone` |
| PRIM-08 | OPI | No | book accepts duplicate opId | `40_transfer.rho:244` | Accepted | the per-owner ledger is the supported path; a direct book call is a caller error, documented |
| PRIM-09 | OPI/ERTP | Late | native transfer reply ignored while op commits | `09_identity.rho:263-277` | Fixed | reply matched, `1/0` on failure; G-NATIVE |
| PRIM-10 | ERTP | Other than | no unsafe post-native catch-all found; remaining `_` branches are pre-effect | §3.11 of the audit | Closed | G-NATIVE prevents regression |
| PRIM-11 | SIG | No | terms stored before sponsor check | `50_market.rho:122-161` | Fixed | `put` verifies the sponsor signature before storing; Lean `marketTerms_putChecked` |
| PRIM-12 | SIG | Before | preimage has no nonce/deadline | `50_market.rho:795-799` | Partial | domain is `rcash:market-create:v1`; a v2 nonce/deadline is a separate change |
| PRIM-13 | Cap | As well as | caller name not mechanically restricted to sinks | all facet sites | Medium | G-FACET; Lean I20 |
| PRIM-14 | DIR | Other than | seal evidence was weaker than the wiring text | `50_market.rho:218`; `30-WIRING.md:204` | Closed | `seal(marketId, auth)` matches the wiring text; Lean I6 |
| PRIM-15 | P1 | Part of | pause+registry two cells; the CAS orders the mirror, but a direct `VaultBook.pause` can diverge | `32_currency_registry.rho:308-356` | Accepted | governors must use `CurrencyRegistry.setPaused`; a projection is a separate design |
| PRIM-16 | P2 | Late | snapshot can be used after an await unvalidated | all P2 arms | Medium | G-PHASE; Lean `p2` |
| PRIM-17 | H2 | Other than | provenance asserted, not enforced | `09_identity`, `31_stablecoin` | Medium | Lean `Prov`; `check_captures` |
| PRIM-18 | P6 | No | graceful refusal after a write not uniformly rejected | all `(false` sites | Medium | G-AFTER; Lean `p6` |
| PRIM-19 | P1 | More | op ledger grows without bound | `09_identity.rho:194-256` | Low | fix R3 cap/prune |
| PRIM-20 | ERTP | Early | no unsafe post-before-reply site found; gate gap only | P4 sites | Closed | G-NATIVE; Lean `p4` |

**Severity:** High = value/liveness/market-bricking or an unsound audited claim; Medium =
retryability/throughput or a proof gap on a live path; Low = hygiene.

### 3.1 Significant worksheets

**PRIM-01 — fail without repost.** Vault arms that detect a `rev` mismatch after a take call
`1/0` without reposting (`31_stablecoin.rho:362,419,1005,1144`). At runtime this is safe only
because the deploy rolls back; the cell law as stated in `00-CALCULUS.md` is a graceful
statement, so the model needs a rollback step to justify the shape. Proof obligation:
`p3_fail_rolls_back`, plus a `Mode.aborted` outcome that the interleaving layer treats as
"world unchanged".

**PRIM-03 — opaque conflict.** A `rev` mismatch after value movement calls `1/0`. The deploy
rolls back, so safety holds, but the client sees "division by zero" and cannot distinguish
contention from a bug. The pre-effect path can return `"conflict"`; the post-effect path
must fail. The Lean obligation is a typed outcome (`Mode.refused reason` vs `Mode.aborted`),
so a conflict cannot be reported as an abort by the model.

**PRIM-08 — book-level opId (accepted).** `TransferBook.send` records the opId but does not
consult an index. The per-owner ledger in `Account.sendTransfer` is the supported dedupe; a
direct book call bypasses it. A per-book index cell would serialise every send on one global
cell, regressing the send concurrency that the per-transfer design provides, so this is an
accepted caller discipline. The Lean `opIndex` obligation remains the shape to prove if a
future book-level index is added.

**PRIM-09 — ignored native reply (fixed).** `sendCommit` used to wait on the
`revVault!transfer` channel with `for (_ <- vCh)`, ignoring `(false, …)`, then call
`finishSend`; a refused stipend still committed the op. This branch matches `Nil`, `true`
and `(true, _)` and calls `1/0` on anything else, so the reservation rolls back. The
permanent guard is G-NATIVE: after a native send, a bare `_ =>` success is an error.

**PRIM-05 — withdrawn.** `LiquidityLock.release` and `.cancel` read `poolNow`, the deployer
key and the REV address *before* `for (@s <- lockState)` (`51_pool.rho:583-658`). There is no
hold across the Clock or a caller facet, so the earlier draft's PRIM-05 is withdrawn.

**PRIM-11/12 — terms and sponsor.** `MarketTerms.put` is content-addressed, bounds-checked
and now authenticated: it computes the canonical hash, rebuilds
`rcash:market-create:v1|marketId|termsHash|sponsor`, verifies the sponsor signature with the
same verifier the factory uses, and only then stores. The preimage is domain-separated but
still has no nonce or deadline; a v2 preimage is a separate change. The Lean obligations are
`marketTerms_putChecked_integrity` (under `CollisionResistant`) and
`verify_true_implies_signer` (under `Unforgeable`).

---

## 4. Deviation → obligation map

Every row must have at least one obligation, fix, gate or accepted-risk reference.

| Obligation | Statement | Covers |
|---|---|---|
| L-P1 `p1_sound` | a P1 program takes and posts exactly once, no await between | PRIM-15 |
| L-P2 `p2_equiv_p1` | a revalidated P2 snapshot is equivalent to P1 at commit | PRIM-16 |
| L-P3 `p3_fail_rolls_back` | an effect then a failed revalidation leaves no post and aborts | PRIM-03, PRIM-04 |
| L-P4 `p4_native_only` | a held cell crosses only native steps | PRIM-04, PRIM-20 (gate) |
| L-P6 `p6_no_graceful_refusal_after_write` | no graceful refusal after a write | PRIM-01, PRIM-02, PRIM-18 |
| L-LIN `par_preserves_linear` | interleaved branches preserve linearity | PRIM-01 |
| L-ATOM `commit_atomic` | a rejected deploy leaves the world unchanged | PRIM-15 |
| L-SER `serialisable_disjoint` | disjoint committed deploys commute | merge model |
| L-REV `rev_monotone` | every mutation increments `rev`; a recheck is sound | PRIM-06, PRIM-07 |
| L-I5 `terms_put_integrity` | stored terms hash is the canonical hash | PRIM-11 |
| L-I6 `directory_well_formed` | sealed ⇒ bound, factory-owned, no orphan | PRIM-14 |
| L-I8 `reporter_set` | three distinct reporters; sponsor at most once | feed policy |
| L-I9 `pair_fresh` | pair rate fresh and within the age bound | PRIM-16 |
| L-I10 `custody_matches` | reserves equal native custody | PRIM-10, PRIM-20 |
| L-I11 `shares_conserved` | totalShares = minted − burned | pool accounting |
| L-I12 `gate_sound` | depth/ticket/trade/tolerance implications | market terms |
| L-I13 `lock_linear` | fund once; release/cancel exclusive | PRIM-01 |
| L-I15 `no_strand` | no payment is stranded on a refusal | PRIM-10 |
| L-I19 `governor_nonce` | threshold and monotone nonce on the real state | PRIM-03 |
| L-I20 `provenance` | caller caps are never stored | PRIM-13, PRIM-17 |
| L-I3 `pair_unique` | one active market per unordered pair | DIR |

| Gate | Rule | Covers |
|---|---|---|
| G-AFTER | after a live take, a refusal reposts or fails; phase ordering | PRIM-01, PRIM-02, PRIM-18 |
| G-REV | every mutating arm increments `rev` or is explicitly exempt — **implemented** in `tools/check_primitives.py` | PRIM-06, PRIM-07 |
| G-OPI | a value-moving book arm consults an op index | PRIM-08 |
| G-FACET | a caller-supplied name is used only on sink arms | PRIM-13, PRIM-17 |
| G-NATIVE | no discarded native reply (`for (_ <- ...)`) and no catch-all success — **implemented** in `tools/check_primitives.py` | PRIM-09, PRIM-10, PRIM-20 |
| G-PHASE | declared `pre`/`commit`/`after_consume` matches take/post order | PRIM-16 |
| G-GUARD | guard `expr` tokens resolve against the source | all guard arms |
| G-EFFECT | effect `target` is written on the commit path | all mutating arms |

**Rholang fixes:** R1 primitive consistency; R2 native boundary; R3 idempotency; R4 authority;
R5 multi-cell atomicity; R6 directory/docs. See the approved plan.

**Gate status:** G-REV, G-NATIVE and G-FACET are blocking in `make formal-check` via
`tools/check_primitives.py`; G-PHASE, G-EFFECT and G-GUARD are blocking via
`tools/check_flows.py --phases --effects --guards`; G-AFTER is the existing after-consume
check; G-OPI is an accepted caller discipline.

---

## 5. Guide-word coverage matrix

`●` = open deviation; `○` = examined, finding fixed or withdrawn (kept for trace);
`–` = examined, none found. A blank would be a method gap.

| Primitive | No | More | Less | As well as | Part of | Reverse | Other than | Early | Late | Before | After |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P-cell | ● | ● | – | ● | ● | ● | ● | – | – | ● | ● |
| Cap | – | ● | – | ● | ● | ● | ● | – | – | – | – |
| G | ● | – | – | – | ● | ● | ● | – | – | ● | ● |
| P1 | – | ● | – | ● | ● | ● | – | – | – | – | – |
| P2 | ● | ● | – | – | – | – | – | – | ● | ● | – |
| P3 | – | ● | – | – | – | – | ● | – | ● | ● | ● |
| P4 | – | ○ | – | – | – | – | – | – | – | – | – |
| REV | ● | – | ● | – | – | ● | ● | – | – | ● | – |
| DIR | ● | – | – | ● | ● | ● | ● | – | – | – | – |
| OPI | ● | ● | – | – | – | ● | ● | – | ○ | ● | – |
| ERTP | ○ | – | – | – | ● | – | ○ | ○ | – | – | – |
| SIG | ● | – | – | ● | ● | – | ● | – | – | ● | – |
| H2 | ● | – | – | ● | – | ● | ● | – | – | – | – |

The matrix is deliberately coarse: it proves the guide words were applied, not that every
combination is a finding. The full worksheet in §2 is the record.

---

## 6. Relationship to the Lean exercise

The HAZOP is **input**, not a parallel exercise:

1. Every open High deviation has an obligation in §4. The obligation is the theorem that,
   if proved about the primitive, makes the deviation unrepresentable in the model.
2. The primitive laws (`p1`–`p6`, WF2–WF5) are proved once, generically, in
   `spec/lean/Rholphin/Prim/`. The 171 arms are expressed as `CellArm`/`Prog` instances and
   inherit the laws; they do not each need a bespoke concurrency proof.
3. The deploy/interleaving layer turns the merge assertion in `HAZOP.md` into
   `commit_atomic` and `serialisable_disjoint`. The HAZOP can then cite a theorem instead
   of a design note.
4. The gates close the remaining gap: a deviation that is not a theorem is at least a
   checker error, so it cannot silently return.

### 6.1 Accepted risks (no fix planned in this programme)

| Risk | Rationale |
|---|---|
| No full Rholang parser | The contracts are protocol-disciplined; a parser is a research track. |
| Cryptography not proved | `CollisionResistant`/`Unforgeable`/`Binding` are explicit hypotheses, not axioms. |
| Native ERTP not modelled | A `NativeTotal` step is assumed; I10/I15 are conditional on it. |
| General conflict-serialisability | Only the disjoint-write case is proved; overlaps are a research question. |
| Direct book call is not idempotent | The book has no shared cell by design; the per-owner ledger is the supported path. |
| A direct `VaultBook.pause` can diverge from the registry | Governor procedure requires `CurrencyRegistry.setPaused`; the `pausedRev` CAS orders the mirror. |
| Phlo/scheduler/liveness | Out of scope; the model is safety-only. |

---

## 7. Sign-off

The register is complete for the static phase when:

- every row in §3 has a disposition and every disposition resolves in §4 or §6.1;
- every open High deviation has a reproducer (a red test, a vector or a flow-checker case);
- the guide-word matrix has no blank cell;
- the Lean obligations are registered in `spec/lean/claims.yaml` and the Rholang fixes are
  tracked by R1–R6;
- an independent reviewer has sampled the High worksheets and the obligation map.
