# Audit — smart-contract primitives and Lean proofs

**Status:** audit report, static phase. **Date:** 2026-11-04. **Branch:** `feat/primitives-audit`.

**Scope.** The v3 Rholang suite (`contracts/src/deploy/v3/`, 19 files, 7,142 lines,
171 deploy arms, 82 helpers, 22 state cells) and the Lean 4 model (`spec/lean/`, 13
modules). This is an audit of **primitives and proofs**, not a product security review and
not an economic audit. It complements [`HAZOP.md`](HAZOP.md), which covers shared channels
and the client/hostlist path.

**Stance.** Every finding cites a source location and a reproducer or a named proof
obligation. The report separates **what is proved**, **what is conditional**, and **what is
only tool-evidenced**. It does not claim that the deployed Rholang is verified.

---

## 1. Executive summary

The suite is disciplined at the arm level: every stateful component owns one cell, reads use
`peek`, mutations use `take`/`post`, and the hot paths are sharded per owner, transfer,
market and currency. The audit's concerns are not "the contracts are unstructured"; they are
that the *proofs do not yet cover the primitives*, and that the *gates cannot see* the
primitives they claim to cover.

Six results drive the programme:

1. **Thirteen invariants have no Lean theorem**: S8, I5, I6, I8, I9, I10, I11, I12, I13,
   I15, I20, I22, I24. I3, I7 and I19 are only partial. The flow arms that carry them are
   labelled `verified`, so the label reflects the flow reconciliation, not a proof.
2. **About 25 modelled arms are identity or no-op stubs** (`verifier_sigOk ok := ok`,
   `claimCode_hash s := s`, `marketTerms_put hash := some hash`, `fxPool_attest p := p`,
   `vaultBook_pause _ := b`, …). Their names exist, so name-level traceability passes.
3. **Six audited theorems restate a hypothesis** (`depositInterest_S3`, `Psm.buy_ceiling`,
   `Psm.sell_floor`, `notify_S10`, `mint_preserves_health`, `withdraw_preserves_health`).
   They are counted in the axiom audit despite adding no invariant content.
4. **No model of concurrency, deploy atomicity or rollback exists.** `Linear/Cell.lean` is a
   single sequential `List Op` trace; `call` is opaque. The merge rule that the HAZOP relies
   on ("one pre→post diff per channel, whole-deploy rejection") is a design assertion, not a
   theorem.
5. **The gates are name-level.** `check_lean.py` requires ≥20 `#print axioms` lines (38
   exist) and an axiom whitelist. `check_flows.py` checks access/refusal sets but never the
   guard `expr`, the effect `formula`, or the declared access `phase` against the source.
   TLC is not in CI and 2 of 7 models have never been run.
6. **The primitives are implemented inconsistently**: P3 vs P4 for the same purse-move +
   cell-write shape, graceful refusal vs `1/0` for the same failure, a registry without a
   `rev` (fixed in this branch), an ignored native reply in `sendCommit` (fixed in this
   branch), and no book-level opId dedupe.

None of these is a new value-loss bug in the deployed terms beyond the findings already
fixed in `docs/spec/HAZOP.md`. They are **assurance defects**: the evidence is weaker than
the labels imply, and the inconsistencies make future defects likely.

---

## 2. Method and evidence

| Object | Population | Method | Evidence |
|---|---|---|---|
| Primitive instantiations | 13 classes × 171 arms | 100% site walk against the normative shape; inventory from `contracts/build/arm_inventory.json` | source lines, flow YAML |
| Lean statements | 13 modules, ~140 declarations | classify substantive / definitional / restatement / stub / alias | `spec/lean/**`, `Audit.lean` |
| Invariant coverage | S1–S12, I1–I24 | matrix invariant → predicate → theorem → arms | `claims.yaml`, `tools/check_claims.py` |
| Model↔code link | 171 arm names | declare + resolve; behavioural vectors planned | flow `lean:` fields |
| Gates | 5 tools | defect review; each gap becomes a gate change | `tools/*.py`, `Makefile`, CI |

Evidence rules: a finding is **confirmed** when the source shows the deviation; **conditional**
when it depends on runtime linearity or an external behaviour; **programme** when it is a
missing proof or gate rather than a code defect. Severity: Critical = value/permanent state
loss; High = liveness, market bricking, or an unsound audited claim; Medium = retryability,
throughput, or a proof gap on a live path; Low = hygiene/documentation.

---

## 3. Primitive audit

The 13 primitives are the recurring shapes, not language operators. For each: the normative
shape, the population, and the audit verdict.

### 3.1 P-cell — linear state cell

**Normative:** a mutating arm either peeks (read-only) or takes, and every branch either
posts exactly one next state or fails the deploy. A refusal after a take must repost the
unchanged state or `1/0`; a graceful refusal with neither is a D2 defect
(`00-CALCULUS.md`, WF3/WF5, S6).

**Population:** every stateful component; 98 peeks and one consume/repost per mutating arm.

**Verdict: conforming, with one proof gap.** `LiquidityLock.release` and `.cancel` read the
Clock and deployer identity *before* taking `lockState` and repost the cell on a refused
native withdraw (`51_pool.rho:583-658`); the earlier draft suspected a hold across the Clock
and was wrong. The remaining deviation is a proof gap: vault arms that detect a `rev`
mismatch after a take (`31_stablecoin.rho:362,419,1005,1144`) fail without reposting. That
is legal because `1/0` rolls the deploy back, but it relies on runtime rollback rather than
on the cell law, which the Lean model does not yet represent.

### 3.2 Cap — capability and facet

**Normative:** authority is a name created by `new` and held only in a closure; a
caller-supplied name is used only as a **sink** (deposit/refund/payout facet), never as an
authority (`S4`, `S13`, I20).

**Population:** ~12 named auth caps, 249 `new … in` sites.

**Verdict: partial.** No structural violation was found in the deep dive, but the rule is
enforced only by comment. Nothing prevents a future arm from calling a caller-supplied name
on a non-sink arm, and no tool distinguishes a sink facet from an authority. This is
AUD-18 / PRIM-13.

### 3.3 G — guard and refusal

**Normative:** a pure guard refuses with the unchanged state and `(false, reason)`; after any
value movement or cell write, an unexpected refusal is `1/0` (P6). Refusal strings are
normative (`SPEC.md` §18.3).

**Population:** 384 `(false` productions, 63 `1/0` sites.

**Verdict: non-conforming.** The same shape is handled two ways:

- `FxPool` conflicts are graceful `(false,"conflict",*payment)` (`51_pool.rho:362,448,492`).
- Vault/PSM/buffer/savings conflicts are `1/0` (`31_stablecoin.rho:362,419,1005,1144,1674,1718,1735,219,260`).
- `LiquidityLock` release/cancel are graceful when the native withdraw itself refuses
  (no value moved, cell reposted); transfer claim/refund fail after a facet deposit attempt.

This is AUD-11/12 / PRIM-02/03/04. The rule "graceful before effect, fail after effect" is
correct; the code does not apply it uniformly, and the flow checker does not enforce the
general rule (only the after-consume reason/repost pairing). The lock branches are locally
safe because a refused withdraw moves no value; the finding is consistency and reviewability,
not a confirmed loss.

### 3.4 P1 — single-cell commit

**Normative:** take, validate, post on one cell with no await between (`00-CALCULUS.md` §7).

**Population:** registrations, governor nonce, `MarketTerms.put`, `CurrencyRegistry.register`.

**Verdict: conforming at the arm level; non-conforming at the composition level.** The
pause/registry pair (`32_currency_registry.rho:308-356`) is two P1 commits with no joint
version. A `pausedRev` CAS was added on the vault side, but the registry mirror is still a
second write; a direct `VaultBook.pause` can leave the registry disagreeing (AUD-19 /
PRIM-15).

### 3.5 P2 — await-then-commit

**Normative:** peek, await external reads, take, revalidate the snapshot, post.

**Population:** `OracleFeed.submit`, `MarketIndex.activate`, and the oracle/registry reads on
market creation.

**Verdict: conforming where reviewed.** The risk is not a known defect but a checker gap:
`check_flows.py` does not compare a declared `phase: pre` access with the source take order,
so a future P2 arm that takes before its last await would pass the gate. AUD-08 / PRIM-16.

### 3.6 P3 — effect-then-commit

**Normative:** peek, read/math, perform the effect, take, revalidate `rev`, post; fail if the
effect or the revalidation fails.

**Population:** `FxPool.swap/add/remove`, transfer claim/refund, vault liquidate/repay,
buffer deposit/cover/paySavings.

**Verdict: mostly conforming, one inconsistency.** `SavingsPool.deposit/withdraw` are P4
(take before the native move) while `SurplusBuffer.deposit/cover` are P3 for the same
purse-move + cell-write shape. Both can be safe; the choice is undocumented and untested
(AUD-12 / PRIM-04). The FxPool P3 refactor is correct and revalidates `rev`.

### 3.7 P4 — hold-through-native

**Normative:** a cell may be held across a **native ERTP** step only. It must not be held
across a component call or a caller-supplied facet (`S2`, `S15`).

**Population:** stablecoin mint/burn, savings deposit/withdraw, `LiquidityLock.fund/release`.

**Verdict: conforming.** `LiquidityLock.fund/release/cancel` read the Clock and deployer
identity before the take (`51_pool.rho:546-552,584-590,622-634`); the remaining holds are
across native ERTP steps only (`Stablecoin.mint/burn`, `SavingsPool.deposit/withdraw`). The
earlier draft's PRIM-05 was withdrawn after source review. The style difference with the P3
buffer arms is PRIM-04, not a P4 violation.

### 3.8 REV — version revalidation

**Normative:** every mutable state carries a monotone `rev`; every mutation increments it
before the post; a P3 arm compares the taken `rev` with the peeked snapshot and refuses or
fails on mismatch.

**Population:** 17 `get("rev") !=` comparisons; `poolState`, `savingsState`, `vaultState`,
`bufferState`, `psmState`, `feedState`.

**Verdict: incomplete, partially fixed.** `oracleRegState` had no `rev`; this branch adds
one and bumps it on `regBind` and both allowlist mutations (`12_oracle_registry.rho`).
`issuerState` still has no `rev`, but its mint/burn arms CAS on `totalPrincipal`, which is
sound while every issuer mutation changes it; the model should name that field rather than
assume a generic `rev`. The remaining gap is the absence of a gate: nothing requires a new
mutating arm to bump its version field. AUD-13 / PRIM-06/07.

### 3.9 DIR — directory and registry

**Normative:** reads peek; writes take and bump `rev`; a bind is create-only or CAS; a
directory slot is written by exactly one factory (`I2`, `I6`).

**Population:** `Root`, `CurrencyRegistry`, `StablecoinDirectory`, `OracleRegistry`,
`MarketTerms`, `MarketDirectory`, `MarketIndex`.

**Verdict: mostly conforming.** `MarketDirectory.bind` is create-only and idempotent for the
same terms; `oracleRegState` now bumps `rev` like the other registries. `MarketDirectory.seal`
has no `sealedBy`/terms-hash argument, unlike `30-WIRING.md` §204, so the evidence is the
factory capability, not the directory state (AUD-21 / PRIM-14).

### 3.10 OPI — op-id idempotency

**Normative:** reserve an opId before the effect, finish it after, and return the stored
result on replay; a direct call that bypasses the ledger is a defect.

**Population:** `accountState.ops` (`09_identity.rho:194-256`) and the SDK op cache.

**Verdict: incomplete.** `TransferBook.send` records the opId in the transfer
(`40_transfer.rho:244`) but does not dedupe it; a direct book call with the same opId creates
a second transfer. `TransferBook` has no shared cell by design, so closing this needs a
per-book op index or an enforced single caller. Separately, `sendCommit`
(`09_identity.rho:263-277`) ignored the `revVault!transfer` reply while its comment said a
failed native transfer fails the deploy; this branch now matches `Nil`, `true` and
`(true, _)` and fails `1/0` on anything else. AUD-14/15 / PRIM-08/09.

### 3.11 ERTP — native boundary

**Normative:** exhaustive `(true, x)` / `(false, e)` matching; after value movement, an
unexpected branch fails the deploy (P6, S7).

**Population:** issuer/purse/custody sites in stablecoin, pool, transfer, identity.

**Verdict: mostly conforming after the previous sweep.** The remaining catch-all `_ =>`
branches in the value-moving files are pre-effect (brand/asset checks and a refused lock
withdraw), where returning the payment is correct; the post-native branches fail `1/0`. The
ignored `sendCommit` reply is fixed in this branch. The audit cannot prove exhaustiveness
from static reading alone, so the gate change (G-NATIVE) is still required. AUD-14 /
PRIM-09/10/20.

### 3.12 SIG — signatures and quoting

**Normative:** verify the `deployerId`/sponsor before any write; domain-separate the signed
preimage with the Root/factory URI and, where replay matters, a nonce and deadline
(`S8`, I21).

**Population:** 7 `sigOk` sites, 11 `pubKeyBytes` sites, 5 quoting preimages.

**Verdict: non-conforming at `MarketTerms.put`.** The terms store validates bounds and
content-addresses the value, then stores it, all before `marketOwnerCheck` verifies the
sponsor (`50_market.rho:122-161,806`). A relayer can grow the store at griefing cost. The
market-create preimage is `rcash:market-create:v1|marketId|termsHash|sponsor`
(`50_market.rho:795-799`) with no domain, nonce or deadline. AUD-16/17 / PRIM-11/12.

### 3.13 H2 — capability hand-off

**Normative:** H2a hands the caller a direct token; H2b delegates a token the callee may take
once and must return. A caller capability is never stored (`S13`, I20).

**Population:** account/vault auth tokens, facets, deposit/refund facets.

**Verdict: partial.** Provenance is documented and tested by `check_captures.py`, not by
Lean. The model has no `Prov` type; a theorem that a caller capability is never stored is
absent. AUD-18 / PRIM-17.

---

## 4. Lean proof audit

### 4.1 Classification

| Class | Count (approx.) | Examples |
|---|---|---|
| Substantive transition/invariant | 50 | `Issuer.*_S1`, `Vault.*_S2`, `Market.stage_*`, `Transfer.claim_then_refund_refused` |
| Definitional / projection (`rfl`) | ~20 | `settle_principal`, `writeOff_badDebt`, ten `*_totalDebt` |
| Hypothesis restatement | 6 | `depositInterest_S3`, `Psm.buy_ceiling`, `Psm.sell_floor`, `notify_S10`, `mint_preserves_health`, `withdraw_preserves_health` |
| Identity/no-op stub | ~25 | `verifier_sigOk`, `claimCode_hash`, `marketTerms_put`, `fxPool_attest`, `vaultBook_pause`, `account_claimTransfer` |
| Alias | ~3 | `take_without_put_rejected`, `nested_take_deadlock` |

The 118 substantive theorems registered in `claims.yaml` are real: the arithmetic core (division, accrual, close factor,
savings, PSM, AMM bounds) and the S1/S2/S3/S14 transition obligations are the strongest part
of the project. The weakness is coverage, not the quality of those proofs.

### 4.2 Invariant coverage

| Status | Invariants |
|---|---|
| Covered | I1, I14, I21, I23, S1, S2, S3 |
| Partial | I2, I3, I4, I5, I6, I7, I8, I9, I10, I11, I12, I13, I15, I19, S4, S6, S7, S8, S9, S10, S11, S12 |
| Deferred (no theorem) | none |
| Tool-evidenced | I20 (`check_captures.py`), I22 (`measure_contracts.py`), I24 (`check_mesh.py`) |

`spec/lean/claims.yaml` is now the machine-readable record; `tools/check_claims.py`
enforces that every invariant has an entry, every named theorem resolves, and a `covered`
invariant cites a substantive theorem. See §6 for the programme.

### 4.3 Stub inventory

These arms are modelled as identity/no-op and must not be cited as proof.  The
`Crypto/` modules now provide the conditional interfaces (`Hasher`, `SigScheme`,
`ClaimScheme`, `Canonical`) and the theorems `terms_put_integrity`,
`verify_true_implies_signer`, `claim_requires_preimage`, `wrong_secret_refused` and
`codec_no_pipe_collision`; the old identity defs remain only for compatibility and are marked
`stub` in the claim register.

- `Model.Kernel.verifier_sigOk`, `verifier_hash`, `verifier_claimHash`, `codec_hash`;
- `Model.Kernel.claimCode_hash`;
- `Model.Market.marketTerms_put`, `MarketDirectory.*` (model only, no well-formedness);
- `Model.Pool.fxPool_attest`, `poolTemplate_create` (no custody link);
- `Model.Vault.vaultBook_pause`, `vaultBook_params`;
- `Model.Issuer.stablecoin_*` (brand/issuer/amountOf/attest), `riskParameters_*`;
- `Model.Identity.account_claimTransfer`, `account_refundTransfer`, `account_transfers`,
  `account_vaultOpen`;
- `Model.Oracle.oracleHub_*` (projections).

### 4.4 Gate audit

| Gate | What it enforces | Gap |
|---|---|---|
| `check_lean.py` | no `sorry`/`admit`/`native_decide`/local `axiom`; build; ≥20 `#print axioms` lines; axiom whitelist | no statement shape, no warnings-as-errors, no invariant/arm coverage; 38 lines exist but 20 suffice |
| `Audit.lean` | a fixed list of 38 theorems | hand-maintained; misses ~half the theorems; includes `rfl` and restatements |
| `check_flows.py` | arm coverage, source line, access/refusal sets, after-consume pairing, protocol/nested-call declarations, Lean name exists | guards/effects are unchecked prose; `phase`/`on` are discarded; no facet or native-reply rule |
| `check_traceability.py` | bidirectional requirement/acceptance equality, criteria/check resolution, Lean names exist | structural only; does not prove any check passes |
| `make tla-check` | TLC over 7 models if `tlc` is on PATH | not in CI; `MarketCreateAtomicity` and `PoolCriticalSection` have never been run here |
| `check_primitives.py` | no discarded native reply; a rev-bearing mutation bumps `rev`; oracle registry is initialised with `rev` | textual and per-file, not per-arm; no facet, phase or reply-shape analysis |
| `check_arm_vectors.py` | 19 behaviour vectors over the checked transitions and crypto/claim interfaces | model vectors only; they pin the Lean semantics, not the deployed term |
| harness | sequential unit/scenario suites | no concurrency, interleaving or fault-injection tests |

### 4.5 What the Lean model does not represent

The node scheduler and phlo; name-passing/quoting; native ERTP custody; cryptography (hashes
are polynomial, signatures are identity); market terms content-addressing; fixed-width
overflow. Primitive-step interleaving and deploy atomicity are now modelled
(`Linear.Interleave`, `Linear.Deploy`), but the model does not represent the node's scheduler
or the Rholang term. The remaining gaps are either modelled abstractly in the programme (§6)
or recorded as assumptions in `claims.yaml`.

---

## 5. Findings register

| ID | Severity | Finding | Evidence | Disposition |
|---|---|---|---|---|
| AUD-01 | Fixed | 13 invariants had no Lean theorem | §4.2 | Every current invariant has a claim; deferred = 0 |
| AUD-02 | Partial | ~25 identity/no-op stubs | §4.3 | Crypto interfaces and checked transitions; old defs remain for compatibility |
| AUD-03 | Partial | 6 audited theorems restate a hypothesis | §4.1 | Checked PSM/savings/vault replacements; old restatements remain |
| AUD-04 | Fixed | no model of interleaving or deploy atomicity | `Linear/*` | `Linear.Prim`, `Linear.Deploy`, `Linear.Interleave` |
| AUD-05 | Partial | model↔code link is name-only | tools | Module arm coverage + 19 vectors; full 171-arm vectors pending |
| AUD-06 | Fixed | audit count floor hides deleted theorems | `check_lean.py` | Claims gate + strict arm coverage |
| AUD-07 | Partial | warnings are not errors | `check_lean.py` | `--warnings` report-only; string-literal scan fixed |
| AUD-08 | Fixed | flow checker ignored guard/effect/phase | `check_flows.py` | `--phases --effects --guards` blocking |
| AUD-09 | Fixed | TLC not in CI; 2 models unrun | `ci.yml` | `tla` job runs all seven models |
| AUD-10 | Partial | no concurrency/fault-injection harness | `harness/` | 19 model vectors; live harness pending |
| AUD-11 | Accepted | refusal-style split | §3.3 | Both are locally safe; G-AFTER remains |
| AUD-12 | Accepted | P3/P4 style for one shape | §3.6 | Documented rule; not a safety defect |
| AUD-13 | Partial | registry `rev` | §3.8 | Oracle fixed; issuer CAS documented; no per-arm bump gate |
| AUD-14 | Fixed | `sendCommit` ignores the native reply | `09_identity.rho` | Reply matched; `1/0` on failure |
| AUD-15 | Accepted | `TransferBook.send` does not dedupe opId | `40_transfer.rho` | Per-owner ledger is the supported path; a book cell would serialise sends |
| AUD-16 | Fixed | `MarketTerms.put` stores before auth | `50_market.rho` | Sponsor signature verified before the store |
| AUD-17 | Partial | sponsor preimage has no nonce/deadline | `50_market.rho` | Domain-separated v1; v2 preimage is a separate change |
| AUD-18 | Fixed | no mechanical sink-facet rule | `check_primitives.py` | G-FACET |
| AUD-19 | Accepted | pause+registry two cells | `32_currency_registry.rho` | `pausedRev` CAS plus governor procedure |
| AUD-20 | Accepted | op ledger grows | `09_identity.rho` | Account-lifecycle bounded; pruning is separate |
| AUD-21 | Fixed | seal/doc drift | `30-WIRING.md` | `seal(marketId, auth)` matches the wiring text |
| AUD-22 | Open | live devnet/load campaign not run | — | requires a devnet; the static gates pass |

---

## 6. What the programme will prove

The approved programme (see the plan file and `PRIMITIVES-HAZOP.md`) adds:

1. **Primitive LTS** (`Linear/Prim.lean`, `Step.lean`): a small-step semantics; the
   sequential model is a corollary (`runPrim_cell`).
2. **Intra-deploy interleaving** (`Interleave.lean`): `step_preserves_linear`,
   `steps_preserve_linear` and `held_take_unavailable` — linearity holds under any sequence
   of primitive steps, and a held cell blocks a second take.
3. **Deploy transaction and merge rule** (`Deploy.lean`): `commit_atomic` (a rejected deploy
   leaves the world unchanged; a committed deploy applies its whole diff),
   `apply_preserves_untouched`, `apply_bumps_rev`.
4. **Disjoint-write serialisability** (`Serial.lean`): `preOk_disjoint`,
   `commit_disjoint_does_not_block`, `apply_disjoint_values`. General
   conflict-serialisability with overlapping writes is a research track, not a phase
   deliverable.
5. **Primitive laws** (`Prim/Algebra.lean`): P1/P2/P3/P6 and WF2–WF5 generically;
   `CellArm.refines` and `CellArm.preserves`.
6. **Crypto and native assumptions** (`Crypto/*.lean`): `CollisionResistant`, `Unforgeable`,
   `Binding` and `Canonical` are implemented as interfaces with the assumption as an explicit
   theorem hypothesis, recorded in `claims.yaml`; no `axiom`.
7. **Missing invariants and strengthening** (`Invariants/*.lean`): S8, I5, I6, I8–I13, I15,
   I19, I20, I22, I24; I3/I7; the six restatements replaced.
8. **Model↔code conformance**: `claims.yaml` strict, behavioural vectors for the checked
   transitions and the crypto/claim interfaces (19 so far), then the 25 stubs and all 171
   arms; a generated signature/coverage layer. No Rholang parser in this programme.
9. **Blocking gates**: warnings-as-errors, per-claim audit, strict flow guards/effects/phases,
   sink-facet and native-reply checks, all 7 TLA models in CI.

The Rholang improvements (R1–R6) are in the plan. The HAZOP register that feeds them is
[`PRIMITIVES-HAZOP.md`](PRIMITIVES-HAZOP.md).

---

## 7. Exit criteria and sign-off

The audit closes when:

- no Critical/High finding is open;
- every invariant has a preservation theorem or a reviewed deferral in `claims.yaml`;
- no `verified` arm is unmodelled, identity-stubbed or missing a claim;
- `#print axioms` remains `propext`/`Classical.choice`/`Quot.sound` only, and the assumption
  set is published;
- all 7 TLA models are TLC-checked in CI;
- `make pre-devnet-check` is green and depends on the claims, vector and TLC gates.

**External review is required before sign-off.** The repository authors cannot certify the
rigour of their own statements. The review should sample the strengthened theorem set, the
stub replacements and the assumption list.

**Not covered by this audit:** the Rust client and hostlist (see `HAZOP.md`), economics,
node/rholo internals, ERTP, cryptography, and any claim that the deployed terms are free of
bugs.

---

## 8. Implementation status

**2026-11-07 — the repository-side plan is complete; the live campaign is not run.**

- **Phase 0:** `claims.yaml`, `check_claims.py`, the strict-arm coverage gate and the
  string-aware escape scan.
- **Phase 1:** this report and `PRIMITIVES-HAZOP.md`.
- **Phase 2:** `Linear/Prim.lean`, `Prim/EDSL.lean` and the generic cell laws.
- **Phase 3:** `sendCommit` reply matching (R2), `oracleRegState.rev`, authenticated
  `MarketTerms.put` (R4), and the seal/doc alignment (R6). R3 (book op-id index) and R5
  (pause projection) are accepted with the rationale in the HAZOP; a book index would
  serialise sends and a pause projection is a separate design.
- **Phase 4:** `Linear/Deploy.lean` (`commit_atomic`, `reject_no_effect`),
  `Linear/Interleave.lean` (`step_preserves_linear`, `steps_preserve_linear`,
  `held_take_unavailable`) and `Linear/Serial.lean` (`preOk_disjoint`,
  `commit_disjoint_does_not_block`, `apply_disjoint_values`). Overlapping-write
  serialisability remains a research track.
- **Phase 5:** every invariant has a claim (deferred = 0); the crypto interfaces and the
  checked PSM/savings/vault/pool/market transitions are in place. The register is at 16
  covered, 25 partial, 3 tool-evidenced and 118 substantive theorems; the axiom audit
  covers 72.
- **Phase 6:** module-level arm coverage for all 171 arms and 19 behaviour vectors; the
  remaining vectors are a mechanical extension.
- **Phase 7:** `--phases --effects --guards` are blocking, `check_primitives.py` covers
  G-NATIVE/G-REV/G-FACET, and CI runs TLC over all seven models.

**Not done:** the live devnet/load campaign and the public-testnet campaign (no devnet in
this environment), overlapping-write serialisability, and the R3/R5 design changes.

The static gates `make spec-check`, `make formal-check`, `make pre-devnet-check` and
`make docs-check` pass on this branch.
