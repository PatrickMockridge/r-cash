import Rholphin.Linear.Prim

/-!
# Linearity under interleaving

`LinearCell` says the held cells are distinct and empty, which is the runtime
invariant a linear store maintains.  `step_preserves_linear` shows that one
primitive step preserves it, and `steps_preserve_linear` lifts that to any
sequence of steps.  Since an interleaving is a sequence of steps (the scheduler
chooses which branch steps next), the linearity result holds under every
interleaving, not only the sequential runner.

`held_take_unavailable` is the blocking law: a held cell cannot be taken by a
second branch.  Together these are the safety half of the intra-deploy race.
-/

namespace Rholphin

/-- The linear-store invariant: held cells are distinct and empty. -/
def LinearCell (s : Store) (h : List CellId) : Prop :=
  h.Nodup ∧ ∀ c, c ∈ h → s.cells c = []

theorem LinearCell.empty_of_mem {s : Store} {h : List CellId}
    (hlin : LinearCell s h) {c : CellId} (hc : c ∈ h) : s.cells c = [] :=
  hlin.2 c hc

/-- In a duplicate-free list, erasing the first occurrence removes the only one. -/
theorem not_mem_erase_self_of_nodup {α : Type} [BEq α] [LawfulBEq α] {a : α} {l : List α}
    (hnd : l.Nodup) : a ∉ l.erase a := by
  induction l with
  | nil => simp [List.erase]
  | cons b l ih =>
      by_cases hba : b == a
      · have h_eq : b = a := by simpa using hba
        subst h_eq
        rw [List.erase_cons_head]
        exact (List.nodup_cons.mp hnd).1
      · rw [List.erase_cons_tail hba]
        have hnd' : l.Nodup := (List.nodup_cons.mp hnd).2
        have hbne : b ≠ a := by simpa using hba
        intro hmem
        rcases List.mem_cons.mp hmem with h_eq | hmem
        · exact hbne h_eq.symm
        · exact ih hnd' hmem

theorem LinearCell.not_mem_of_full {s : Store} {h : List CellId}
    (hlin : LinearCell s h) {c : CellId} {v : Nat} (hcell : s.cells c = [v]) :
    c ∉ h := by
  intro hc
  have hempty := hlin.2 c hc
  rw [hcell] at hempty
  simp at hempty

/-- A primitive step preserves `LinearCell`. -/
theorem step_preserves_linear {c c' : Config} {p : Prim}
    (hstep : Step c p c') (hlin : LinearCell c.store c.held) :
    LinearCell c'.store c'.held := by
  cases hstep with
  | peek_ok _ => exact hlin
  | take_ok hcell =>
      refine ⟨?_, ?_⟩
      · rw [List.nodup_cons]
        refine ⟨?_, hlin.1⟩
        intro hc
        have hempty := hlin.2 _ hc
        rw [hcell] at hempty
        simp at hempty
      · intro d hd
        rw [List.mem_cons] at hd
        rcases hd with rfl | hd
        · simp [Store.set]
        · simp only [Store.set]
          split
          · rfl
          · exact hlin.2 d hd
  | put_ok hempty hheld =>
      refine ⟨?_, ?_⟩
      · exact List.Nodup.erase _ hlin.1
      · intro d hd
        simp only [Store.set]
        split
        · rename_i heq
          exact (not_mem_erase_self_of_nodup hlin.1 (heq ▸ hd)).elim
        · exact hlin.2 d (List.mem_of_mem_erase hd)
  | call_ok _ => exact hlin
  | refuse_ok => exact hlin
  | fail_ok => exact hlin

/-- A held cell cannot be taken by another branch. -/
theorem held_take_unavailable {s : Store} {h : List CellId} {m : Mode} {r : Nat}
    (hlin : LinearCell s h) {cell : CellId} (hheld : cell ∈ h) :
    ¬ ∃ c', Step ⟨s, h, m, r⟩ (.take cell) c' := by
  rintro ⟨c', hs⟩
  cases hs with
  | take_ok hcell =>
      have hempty := hlin.2 cell hheld
      rw [hcell] at hempty
      simp at hempty

/-- A sequence of primitive steps (one branch). -/
inductive Steps : Config → List Prim → Config → Prop where
  | nil (c : Config) : Steps c [] c
  | cons {c c' c'' : Config} {p : Prim} {ps : List Prim}
      (h : Step c p c') (hs : Steps c' ps c'') : Steps c (p :: ps) c''

/-- Linearity is preserved by every step sequence, hence by every interleaving. -/
theorem steps_preserve_linear {c c' : Config} {ps : List Prim}
    (h : Steps c ps c') (hlin : LinearCell c.store c.held) :
    LinearCell c'.store c'.held := by
  induction h with
  | nil => exact hlin
  | cons hstep _ ih => exact ih (step_preserves_linear hstep hlin)

end Rholphin
