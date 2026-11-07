import Rholphin.Linear.Deploy

/-!
# Disjoint-write serialisability

Full conflict-serialisability with overlapping write sets is a research
question.  The case the merge rule actually needs is the disjoint one: a
committed deploy cannot change another deploy's precondition or the values it
writes.  These lemmas are the two-deploy core of `serialisable_disjoint`.
-/

namespace Rholphin

theorem list_all_congr {l : List CellId} {f g : CellId → Bool}
    (h : ∀ c, c ∈ l → f c = g c) : l.all f = l.all g := by
  induction l with
  | nil => rfl
  | cons a as ih =>
      simp only [List.all]
      rw [h a (by simp)]
      congr 1
      exact ih (fun c hc => h c (by simp [hc]))

/-- A committed diff leaves the revisions outside its write set untouched. -/
theorem apply_preserves_rev {w w' : World} {d : Diff}
    (h : d.apply w = some w') (c : CellId) (hc : c ∉ d.writes) :
    w'.rev c = w.rev c := by
  by_cases hp : d.preOk w = true
  · simp [Diff.apply, hp] at h
    rw [← h]
    simp [hc]
  · simp [Diff.apply, hp] at h

/-- A committed deploy does not change a disjoint deploy's precondition. -/
theorem preOk_disjoint {w w1 : World} {d1 d2 : Diff}
    (h1 : d1.apply w = some w1)
    (hdisj : ∀ c, c ∈ d1.writes → c ∈ d2.writes → False) :
    d2.preOk w1 = d2.preOk w := by
  unfold Diff.preOk
  apply list_all_congr
  intro c hc
  have hnot : c ∉ d1.writes := fun hc1 => hdisj c hc1 hc
  rw [apply_preserves_rev h1 c hnot]

/-- If a disjoint deploy's precondition held before, it still holds after. -/
theorem commit_disjoint_does_not_block {w w1 : World} {d1 d2 : Diff}
    (h1 : d1.apply w = some w1)
    (hdisj : ∀ c, c ∈ d1.writes → c ∈ d2.writes → False)
    (h2 : d2.preOk w = true) :
    ∃ w2, d2.apply w1 = some w2 := by
  have hp := preOk_disjoint h1 hdisj
  have h2' : d2.preOk w1 = true := by rw [hp]; exact h2
  exact ⟨_, by unfold Diff.apply; rw [if_pos h2']⟩

/-- A committed deploy leaves a disjoint deploy's written values untouched. -/
theorem apply_disjoint_values {w w1 : World} {d1 d2 : Diff}
    (h1 : d1.apply w = some w1)
    (hdisj : ∀ c, c ∈ d1.writes → c ∈ d2.writes → False)
    {c : CellId} (hc : c ∈ d2.writes) :
    w1.val c = w.val c :=
  apply_preserves_untouched h1 c (fun hc1 => hdisj c hc1 hc)

end Rholphin
