import Rholphin.Linear.Cell

/-!
# Helper protocols

The flow specification names three helper classes.  This module states them as
trace shapes and proves that each shape is well formed and posts exactly once.

* H1  — the helper is pure: it has no cell operations.
* H2a — the caller takes the cell; the helper posts the new value; the caller
        does not post again.
* H2b — the helper takes and posts the cell; the caller only peeks.
-/

namespace Rholphin

open Op

/-- Count operations satisfying a predicate. -/
def countOp (p : Op → Bool) : List Op → Nat
  | [] => 0
  | op :: rest => (if p op then 1 else 0) + countOp p rest

def isPut : Op → Bool
  | Op.put _ _ => true
  | _ => false

def isTake : Op → Bool
  | Op.take _ => true
  | _ => false

/-- H1: a pure helper has no cell operations. -/
theorem h1_pure (s : Store) (h : List CellId) :
    run s h [] = some (s, h) := rfl

/-- H2a: caller takes, helper posts once; the held set is empty afterwards. -/
theorem h2a_caller_token {s : Store} {c : CellId} {v : Nat}
    (hcell : s.cells c = [v]) :
    run s [] [Op.take c, Op.put c v] = some ((s.set c []).set c [v], []) := by
  rw [take_put_commit hcell (by simp)]
  simp

/-- H2b: helper takes and posts; the caller's peek is harmless. -/
theorem h2b_delegated {s : Store} {c : CellId} {v : Nat}
    (hcell : s.cells c = [v]) :
    run s [] [Op.peek c, Op.take c, Op.put c v]
      = some ((s.set c []).set c [v], []) := by
  rw [show [Op.peek c, Op.take c, Op.put c v]
        = [Op.peek c] ++ [Op.take c, Op.put c v] from rfl, run_append]
  simp [run, hcell, h2a_caller_token hcell]

/-- The canonical commit has exactly one take and one post. -/
theorem commit_counts (c : CellId) (v : Nat) :
    countOp isTake [Op.take c, Op.put c v] = 1 ∧
    countOp isPut [Op.take c, Op.put c v] = 1 := by
  constructor <;> simp [countOp, isTake, isPut]

end Rholphin
