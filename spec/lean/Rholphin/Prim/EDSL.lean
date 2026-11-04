import Rholphin.Linear.Prim

/-!
# Primitive algebra

A small program language over `Prim`, and the generic `CellArm` shape that the
deploy arms instantiate.  The point is to prove the cell law once and let the
171 arms inherit it, rather than restating it per arm.

`CellArm.preserves` is the obligation that a guard/effect pair maintains a
predicate; `CellArm.denote` is the pure transition the model uses.  The
`Prog` layer is the operational counterpart.  `Refines` states that an
implementation's observable outcome is the program's denotation.
-/

namespace Rholphin

/-- A primitive program.  `branch` is a compile-time choice; a guard that
depends on the state is written as `branch (decide p) ...` in the instance. -/
inductive Prog where
  | done
  | step (p : Prim) (k : Prog)
  | branch (b : Bool) (yes no : Prog)
  | reply (n : Nat) (k : Prog)
  | abort

/-- Denotation of a program over one configuration. -/
def Prog.denote : Prog → Config → Option Config
  | .done, c => some c
  | .step p k, c =>
      match runPrim c [p] with
      | some c' => Prog.denote k c'
      | none => none
  | .branch b yes no, c => if b then Prog.denote yes c else Prog.denote no c
  | .reply n k, c => Prog.denote k { c with replies := c.replies + n }
  | .abort, c => some { c with mode := .aborted }

/-- An implementation refines a program when every observed outcome is the
program's denotation. -/
def Refines (impl : Config → Option Config) (prog : Prog) : Prop :=
  ∀ c c', impl c = some c' → Prog.denote prog c = some c'

/-- The pure cell-arm shape: a guard, a refusal reason, an effect and the
predicate the arm is supposed to preserve. -/
structure CellArm (σ : Type) where
  guard : σ → Bool
  reason : Nat
  effect : σ → σ
  inv : σ → Prop

namespace CellArm

/-- The pure transition of an arm. -/
def denote (a : CellArm σ) (s : σ) : Option σ :=
  if a.guard s then some (a.effect s) else none

/-- A guarded effect preserves the arm invariant.  This is the generic form of
every `*_S*` preservation theorem for a single-cell arm. -/
theorem preserves (a : CellArm σ)
    (h : ∀ s, a.inv s → a.guard s = true → a.inv (a.effect s)) :
    ∀ s s', a.denote s = some s' → a.inv s → a.inv s' := by
  intro s s' hd hi
  unfold denote at hd
  split at hd
  · rename_i hg
    injection hd with heq
    subst heq
    exact h s hi hg
  · contradiction

/-- A refused arm leaves the state untouched. -/
theorem refuse_keeps (a : CellArm σ) (s : σ) (hg : a.guard s = false) :
    a.denote s = none := by
  simp [denote, hg]

end CellArm

/-! ## Primitive laws -/

/-- A take followed by a put of the same cell balances the held set. -/
theorem take_put_balance (c : Config) (cell : CellId) (v : Nat) :
    runPrim c [.take cell, .put cell v] =
      (match c.store.cells cell with
       | [_] => some { c with store := (c.store.set cell []).set cell [v]
                            , held := c.held }
       | _ => none) := by
  cases hc : c.store.cells cell with
  | nil => simp [runPrim, hc]
  | cons x tl =>
      cases tl with
      | nil => simp [runPrim, hc]
      | cons y ys => simp [runPrim, hc]

/-- A graceful refusal is quiescent: it changes neither the store nor the held
set, and it is only available while the branch is running. -/
theorem refuse_quiescent {c c' : Config} {reason : Nat}
    (h : runPrim c [.refuse reason] = some c') :
    c'.store = c.store ∧ c'.held = c.held ∧ c.mode = .running := by
  by_cases hm : c.mode = .running
  · simp [runPrim, hm] at h
    subst h
    exact ⟨rfl, rfl, hm⟩
  · simp [runPrim, hm] at h

/-- A deploy abort is fail-closed: the store and held set are unchanged, and
the mode is `aborted`. -/
theorem fail_aborts {c c' : Config} (h : runPrim c [.fail] = some c') :
    c'.store = c.store ∧ c'.held = c.held ∧ c'.mode = .aborted := by
  simp [runPrim] at h
  subst h
  exact ⟨rfl, rfl, rfl⟩

end Rholphin
