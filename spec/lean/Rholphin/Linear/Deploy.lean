import Rholphin.Linear.Prim

/-!
# Deploy transactions

rholo's merge rule is one pre→post diff per channel and a whole-deploy rejection
on conflict (`docs/spec/HAZOP.md` §1).  This module makes that rule a theorem
rather than a design note.

`World` is the committed store plus per-cell revisions.  A `Diff` names its read
and write sets, the revisions it observed and the values it wants to write.
`Diff.apply` commits only if every written cell still has the observed revision;
otherwise it returns `none`.  `Commit` is therefore a relation with exactly two
outcomes: the whole diff is applied, or the world is unchanged.

The model is deliberately abstract: it does not model phlo, the scheduler or the
Rholang term.  It is the transaction boundary the primitive laws live inside.
-/

namespace Rholphin

abbrev Rev := Nat

structure World where
  rev : CellId → Rev
  val : CellId → List Nat

/-- A single pre→post diff. `pre` is the revision the deploy observed. -/
structure Diff where
  reads : List CellId
  writes : List CellId
  pre : CellId → Rev
  post : CellId → List Nat
  outcome : Mode

/-- The observed revisions still hold for every written cell. -/
def Diff.preOk (w : World) (d : Diff) : Bool :=
  d.writes.all (fun c => w.rev c == d.pre c)

/-- Apply the whole diff or reject the deploy. -/
def Diff.apply (w : World) (d : Diff) : Option World :=
  if d.preOk w then
    some
      { rev := fun c => if c ∈ d.writes then w.rev c + 1 else w.rev c
      , val := fun c => if c ∈ d.writes then d.post c else w.val c }
  else none

structure Deploy where
  id : Nat
  diff : Diff

/-- A deploy either commits its whole diff or is rejected whole. -/
inductive Commit (w : World) : Deploy → World → Prop where
  | accept {d w'} (h : d.diff.apply w = some w') : Commit w d w'
  | reject {d} (h : d.diff.apply w = none) : Commit w d w

/-- The atomicity theorem: no partial commit is reachable. -/
theorem commit_atomic {w w' : World} {d : Deploy} (h : Commit w d w') :
    (w' = w ∧ d.diff.apply w = none) ∨
      (∃ w'', d.diff.apply w = some w'' ∧ w' = w'') := by
  cases h with
  | accept ha => exact Or.inr ⟨_, ha, rfl⟩
  | reject hr => exact Or.inl ⟨rfl, hr⟩

/-- A committed diff leaves every cell outside its write set untouched. -/
theorem apply_preserves_untouched {w w' : World} {d : Diff}
    (h : d.apply w = some w') (c : CellId) (hc : c ∉ d.writes) :
    w'.val c = w.val c := by
  by_cases hp : d.preOk w = true
  · simp [Diff.apply, hp] at h
    rw [← h]
    simp [hc]
  · simp [Diff.apply, hp] at h

/-- A committed diff advances the revision of each written cell by one. -/
theorem apply_bumps_rev {w w' : World} {d : Diff}
    (h : d.apply w = some w') (c : CellId) (hc : c ∈ d.writes) :
    w'.rev c = w.rev c + 1 := by
  by_cases hp : d.preOk w = true
  · simp [Diff.apply, hp] at h
    rw [← h]
    simp [hc]
  · simp [Diff.apply, hp] at h

/-- A well-formed deploy writes each cell at most once. -/
def Diff.WellFormed (d : Diff) : Prop := d.writes.Nodup

theorem one_diff_per_channel {d : Diff} (h : d.WellFormed) : d.writes.Nodup := h

end Rholphin
