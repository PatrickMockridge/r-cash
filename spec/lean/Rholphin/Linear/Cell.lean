import Rholphin.Basic

/-!
# Linear state cells

A state cell is a list with at most one element.  `peek` requires a live value
and leaves the store unchanged; `take` requires exactly one value and empties
the cell, adding it to the held multiset; `put` requires the cell to be empty
and held.  `call` is a nested deployment step and may not touch a held cell.

The defect classes are proved as rejection theorems:

* D1 `peek_then_put_rejected` — a post without a take leaves two cells;
* D2 `take_without_put_not_wf` — a graceful stop after a take loses the cell;
* D3 `nested_call_rejected` — a nested call on a held cell blocks.

Nothing in this module mentions Rholang; the deploy source is related to it by
the arm inventory and the access annotations in `docs/spec/flows`.
-/

namespace Rholphin

abbrev CellId := Nat

structure Store where
  cells : CellId → List Nat

namespace Store

def empty : Store := ⟨fun _ => []⟩

def set (s : Store) (c : CellId) (v : List Nat) : Store :=
  ⟨fun x => if x = c then v else s.cells x⟩

@[simp] theorem set_same (s : Store) (c : CellId) (v : List Nat) :
    (s.set c v).cells c = v := by
  simp [set]

theorem set_other (s : Store) (c d : CellId) (v : List Nat) (h : d ≠ c) :
    (s.set c v).cells d = s.cells d := by
  simp [set, h]

end Store

inductive Op where
  | peek (c : CellId)
  | take (c : CellId)
  | put (c : CellId) (v : Nat)
  | call (c : CellId)

/-- Run a trace.  A failure is `none`; a graceful stop returns the held set. -/
def run : Store → List CellId → List Op → Option (Store × List CellId)
  | s, h, [] => some (s, h)
  | s, h, Op.peek c :: rest =>
      if s.cells c = [] then none else run s h rest
  | s, h, Op.take c :: rest =>
      match s.cells c with
      | [v] => run (s.set c []) (c :: h) rest
      | _ => none
  | s, h, Op.put c v :: rest =>
      if s.cells c = [] ∧ c ∈ h then run (s.set c [v]) (h.erase c) rest else none
  | s, h, Op.call c :: rest =>
      if c ∈ h then none else run s h rest

/-- A trace is well formed when it stops with nothing held. -/
def WF (s : Store) (h : List CellId) (ops : List Op) : Prop :=
  ∃ s' h', run s h ops = some (s', h') ∧ h' = []

/-! ## Rejection theorems -/

/-- D1: peeking then posting the same cell is not a committed update. -/
theorem peek_then_put_rejected {s : Store} {h : List CellId} {c : CellId} {v : Nat}
    (hne : s.cells c ≠ []) :
    run s h [Op.peek c, Op.put c v] = none := by
  simp [run, hne]

/-- D1 (same shape): a post with no take at all is rejected. -/
theorem put_without_take_rejected {s : Store} {h : List CellId} {c : CellId} {v : Nat}
    (hempty : s.cells c = []) (hnot : c ∉ h) :
    run s h [Op.put c v] = none := by
  simp [run, hnot]

/-- D2: a graceful stop after a take leaves the cell held. -/
theorem take_without_put_not_wf {s : Store} {h : List CellId} {c : CellId} {v : Nat}
    (hcell : s.cells c = [v]) : ¬ WF s h [Op.take c] := by
  intro hwf
  rcases hwf with ⟨s', h', hrun, hstop⟩
  simp [run, hcell] at hrun
  rcases hrun with ⟨rfl, rfl⟩
  simp at hstop

/-- D3: a nested call on a held cell is blocked. -/
theorem nested_call_rejected {s : Store} {h : List CellId} {c : CellId}
    (hheld : c ∈ h) :
    run s h [Op.call c] = none := by
  simp [run, hheld]

/-- A take then a put is the one committed update. -/
theorem take_put_commit {s : Store} {h : List CellId} {c : CellId} {v : Nat}
    (hcell : s.cells c = [v]) (hnot : c ∉ h) :
    run s h [Op.take c, Op.put c v]
      = some ((s.set c []).set c [v], h.erase c) := by
  simp [run, hcell, hnot, Store.set]
  rw [List.erase_of_not_mem hnot]

/-- I1: an empty trace is quiescent. -/
theorem wf_quiescent (s : Store) : WF s [] [] :=
  ⟨s, [], rfl, rfl⟩

/-- Alias used by the cell flow specification. -/
theorem take_without_put_rejected {s : Store} {h : List CellId} {c : CellId} {v : Nat}
    (hcell : s.cells c = [v]) : ¬ WF s h [Op.take c] :=
  take_without_put_not_wf hcell

/-- Alias used by the cell flow specification. -/
theorem nested_take_deadlock {s : Store} {h : List CellId} {c : CellId}
    (hheld : c ∈ h) : run s h [Op.call c] = none :=
  nested_call_rejected hheld

/-- D2, contrapositive: if a trace takes and then stops, adding the matching
put makes it well formed. -/
theorem take_then_put_wf {s : Store} {c : CellId} {v : Nat}
    (hcell : s.cells c = [v]) :
    WF s [] [Op.take c, Op.put c v] := by
  refine ⟨(s.set c []).set c [v], [], ?_, rfl⟩
  simp [run, hcell, Store.set]

/-! ## Composition -/

/-- Running a concatenation is running the first trace and then the second
from the resulting store and held set. -/
theorem run_append (s : Store) (h : List CellId) (a b : List Op) :
    run s h (a ++ b) = (run s h a).bind (fun (p : Store × List CellId) =>
      run p.1 p.2 b) := by
  induction a generalizing s h with
  | nil => simp [run]
  | cons op rest ih =>
      cases op with
      | peek c =>
          simp only [List.cons_append, run]
          split
          · simp
          · exact ih s h
      | take c =>
          simp only [List.cons_append, run]
          split
          · exact ih _ _
          · simp
      | put c v =>
          simp only [List.cons_append, run]
          split
          · exact ih _ _
          · simp
      | call c =>
          simp only [List.cons_append, run]
          split
          · simp
          · exact ih s h

/-- Well-formed traces compose. -/
theorem wf_compose {s : Store} {h : List CellId} {a b : List Op}
    (ha : ∃ s₁ h₁, run s h a = some (s₁, h₁))
    (hb : ∀ s₁ h₁, run s h a = some (s₁, h₁) → WF s₁ h₁ b) :
    WF s h (a ++ b) := by
  rcases ha with ⟨s₁, h₁, hrun⟩
  rcases hb s₁ h₁ hrun with ⟨s₂, h₂, hrun₂, hstop⟩
  refine ⟨s₂, h₂, ?_, hstop⟩
  rw [run_append, hrun]
  simp [hrun₂]

end Rholphin
