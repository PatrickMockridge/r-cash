import Rholphin.Linear.Cell

/-!
# Primitive operational semantics

`Linear.Cell` gives a sequential trace over `Op`.  This module gives the
small-step primitive relation that the deploy protocols are stated over:
`peek`, `take`, `put`, an opaque pinned `call`, a graceful `refuse` and the
fail-closed `fail`.

The sequential runner `runPrim` is deliberately defined with the same guards as
`Linear.run`, so the old trace model embeds in the new one (`runPrim_cell`).
The small-step relation `Step` is the object the protocol laws quantify over;
`runPrim` is its deterministic closure for a single branch.  Concurrency is
added in `Linear.Interleave`; deploy atomicity in `Linear.Deploy`.
-/

namespace Rholphin

/-- Outcome of a primitive branch. -/
inductive Mode where
  | running
  | refused (reason : Nat)
  | aborted
  | done
  deriving DecidableEq, Repr

/-- A primitive program step. `call` is a pinned nested helper; its body is
executed by `runPrim` but is opaque to the single-cell laws. -/
inductive Prim where
  | peek (c : CellId)
  | take (c : CellId)
  | put (c : CellId) (v : Nat)
  | call (c : CellId) (body : List Prim)
  | refuse (reason : Nat)
  | fail

/-- Embed the sequential trace operations. -/
def Op.toPrim : Op → Prim
  | .peek c => .peek c
  | .take c => .take c
  | .put c v => .put c v
  | .call c => .call c []

/-- A configuration: store, held cells, mode and reply count. -/
structure Config where
  store : Store
  held : List CellId
  mode : Mode
  replies : Nat

/-- The small-step primitive relation.  `refuse` is only available while the
branch is running; `fail` is always available and aborts the deploy. -/
inductive Step : Config → Prim → Config → Prop where
  | peek_ok {s h m r c} (hne : s.cells c ≠ []) :
      Step ⟨s, h, m, r⟩ (.peek c) ⟨s, h, m, r⟩
  | take_ok {s h m r c v} (hcell : s.cells c = [v]) :
      Step ⟨s, h, m, r⟩ (.take c) ⟨s.set c [], c :: h, m, r⟩
  | put_ok {s h m r c v} (hempty : s.cells c = []) (hheld : c ∈ h) :
      Step ⟨s, h, m, r⟩ (.put c v) ⟨s.set c [v], h.erase c, m, r⟩
  | call_ok {s h m r c body} (hnot : c ∉ h) :
      Step ⟨s, h, m, r⟩ (.call c body) ⟨s, h, m, r⟩
  | refuse_ok {s h r reason} :
      Step ⟨s, h, .running, r⟩ (.refuse reason) ⟨s, h, .refused reason, r + 1⟩
  | fail_ok {s h m r} :
      Step ⟨s, h, m, r⟩ .fail ⟨s, h, .aborted, r⟩

/-- Deterministic closure of one branch.  `refuse` and `fail` are terminal. -/
def runPrim : Config → List Prim → Option Config
  | c, [] => some c
  | c, .peek cell :: rest =>
      if c.store.cells cell = [] then none else runPrim c rest
  | c, .take cell :: rest =>
      match c.store.cells cell with
      | [_] => runPrim ⟨c.store.set cell [], cell :: c.held, c.mode, c.replies⟩ rest
      | _ => none
  | c, .put cell v :: rest =>
      if c.store.cells cell = [] ∧ cell ∈ c.held then
        runPrim ⟨c.store.set cell [v], c.held.erase cell, c.mode, c.replies⟩ rest
      else none
  | c, .call cell body :: rest =>
      if cell ∈ c.held then none
      else
        match runPrim c body with
        | some c' => runPrim c' rest
        | none => none
  | c, .refuse reason :: _rest =>
      if c.mode = .running then some ⟨c.store, c.held, .refused reason, c.replies + 1⟩
      else none
  | c, .fail :: _rest => some ⟨c.store, c.held, .aborted, c.replies⟩

/-- The sequential trace embeds in the primitive runner. -/
theorem runPrim_cell (s : Store) (h : List CellId) (ops : List Op) :
    runPrim ⟨s, h, .running, 0⟩ (ops.map Op.toPrim) =
      (run s h ops).map (fun p : Store × List CellId => ⟨p.1, p.2, .running, 0⟩) := by
  induction ops generalizing s h with
  | nil => simp [runPrim, run]
  | cons op rest ih =>
      cases op with
      | peek c =>
          by_cases hp : s.cells c = []
          · simp [Op.toPrim, runPrim, run, hp]
          · simp [Op.toPrim, runPrim, run, hp]
            exact ih s h
      | take c =>
          cases hc : s.cells c with
          | nil => simp [Op.toPrim, runPrim, run, hc]
          | cons v tl =>
              cases tl with
              | nil =>
                  simp [Op.toPrim, runPrim, run, hc]
                  exact ih (s.set c []) (c :: h)
              | cons w ws => simp [Op.toPrim, runPrim, run, hc]
      | put c v =>
          by_cases hp : s.cells c = [] ∧ c ∈ h
          · simp [Op.toPrim, runPrim, run, hp]
            exact ih (s.set c [v]) (h.erase c)
          · simp [Op.toPrim, runPrim, run, hp]
      | call c =>
          by_cases hp : c ∈ h
          · simp [Op.toPrim, runPrim, run, hp]
          · simp [Op.toPrim, runPrim, run, hp]
            exact ih s h

/-- `Linear.WF` is `runPrim` finishing with nothing held. -/
def PrimWF (c : Config) (prog : List Prim) : Prop :=
  ∃ c', runPrim c prog = some c' ∧ c'.held = []

end Rholphin
