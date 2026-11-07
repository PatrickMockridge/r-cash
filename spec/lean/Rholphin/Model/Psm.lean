import Rholphin.Model.Issuer
import Rholphin.Arith.Psm

/-!
# PSM state transitions

`stableDebt` is signed.  A buy adds exactly the minted `stableOut`; a sell
subtracts exactly the burned amount.  S11's supply side is the ledger theorem
`Model.Issuer.psmBuy_S3` / `psmSell_S3`; this module states the debt bounds.

The lower bound `stableDebt - amount >= -maxSupply` is the P1 obligation: the
deploy source does not enforce it, so `sellWithinFloor` is a *required* guard
that must be added to the arm before the transition is conformant.
-/

namespace Rholphin.Model.Psm

open Rholphin

def buy (p : Psm) (stableOut : Int) : Psm :=
  { p with stableDebt := p.stableDebt + stableOut }

def sell (p : Psm) (amount : Int) : Psm :=
  { p with stableDebt := p.stableDebt - amount }

theorem buy_ceiling {p : Psm} {stableOut : Int}
    (h : p.stableDebt + stableOut ≤ (p.ceiling : Int)) :
    (buy p stableOut).stableDebt ≤ (p.ceiling : Int) := h

theorem sell_decreases (p : Psm) (amount : Int) (h : 0 ≤ amount) :
    (sell p amount).stableDebt ≤ p.stableDebt := by
  dsimp only [sell]
  omega

/-- P1: the required lower bound on a sell. -/
def sellWithinFloor (p : Psm) (amount : Int) : Prop :=
  -((p.maxSupply : Int)) ≤ p.stableDebt - amount

theorem sell_floor {p : Psm} {amount : Int} (h : sellWithinFloor p amount) :
    -((p.maxSupply : Int)) ≤ (sell p amount).stableDebt := h

theorem sell_preserves_ceiling {p : Psm} {amount : Int}
    (hceil : p.stableDebt ≤ (p.ceiling : Int)) (hpos : 0 ≤ amount) :
    (sell p amount).stableDebt ≤ (p.ceiling : Int) := by
  have := sell_decreases p amount hpos
  omega

/-- A buy is accepted only for a non-negative amount within the ceiling. -/
def buyOk (p : Psm) (stableOut : Int) : Bool :=
  decide (0 ≤ stableOut ∧ p.stableDebt + stableOut ≤ (p.ceiling : Int))

def buyChecked (p : Psm) (stableOut : Int) : Option Psm :=
  if buyOk p stableOut then some (buy p stableOut) else none

theorem buyChecked_refuses_negative {p : Psm} {stableOut : Int} (h : stableOut < 0) :
    buyChecked p stableOut = none := by
  unfold buyChecked
  have hok : buyOk p stableOut = false := by
    unfold buyOk
    exact decide_eq_false (by intro hg; omega)
  simp [hok]

theorem buyChecked_ceiling {p p' : Psm} {stableOut : Int}
    (h : buyChecked p stableOut = some p') :
    p'.stableDebt ≤ (p.ceiling : Int) := by
  unfold buyChecked at h
  split at h
  · rename_i hok
    have hdec : decide (0 ≤ stableOut ∧ p.stableDebt + stableOut ≤ (p.ceiling : Int)) = true := by
      simpa [buyOk] using hok
    have hg : 0 ≤ stableOut ∧ p.stableDebt + stableOut ≤ (p.ceiling : Int) :=
      of_decide_eq_true hdec
    injection h with heq
    subst heq
    dsimp [buy]
    exact hg.2
  · contradiction

theorem buyChecked_adds {p p' : Psm} {stableOut : Int}
    (h : buyChecked p stableOut = some p') :
    p'.stableDebt = p.stableDebt + stableOut := by
  unfold buyChecked at h
  split at h
  · injection h with heq
    subst heq
    rfl
  · contradiction

/-- A sell is accepted only for a non-negative amount within the floor. -/
def sellOk (p : Psm) (amount : Int) : Bool :=
  decide (0 ≤ amount ∧ -((p.maxSupply : Int)) ≤ p.stableDebt - amount)

def sellChecked (p : Psm) (amount : Int) : Option Psm :=
  if sellOk p amount then some (sell p amount) else none

theorem sellChecked_refuses_below_floor {p : Psm} {amount : Int}
    (h : ¬ sellWithinFloor p amount) : sellChecked p amount = none := by
  unfold sellChecked
  have hok : sellOk p amount = false := by
    unfold sellOk
    exact decide_eq_false (by
      intro hg
      exact h (by simpa [sellWithinFloor] using hg.2))
  simp [hok]

theorem sellChecked_floor {p p' : Psm} {amount : Int}
    (h : sellChecked p amount = some p') :
    -((p.maxSupply : Int)) ≤ p'.stableDebt := by
  unfold sellChecked at h
  split at h
  · rename_i hok
    have hdec : decide (0 ≤ amount ∧ -((p.maxSupply : Int)) ≤ p.stableDebt - amount) = true := by
      simpa [sellOk] using hok
    have hg : 0 ≤ amount ∧ -((p.maxSupply : Int)) ≤ p.stableDebt - amount :=
      of_decide_eq_true hdec
    injection h with heq
    subst heq
    dsimp [sell]
    exact hg.2
  · contradiction

theorem sellChecked_subtracts {p p' : Psm} {amount : Int}
    (h : sellChecked p amount = some p') :
    p'.stableDebt = p.stableDebt - amount := by
  unfold sellChecked at h
  split at h
  · injection h with heq
    subst heq
    rfl
  · contradiction

/-! ## Arm-level surface -/

def pegStabilityModule_fundRev (rev amount : Nat) : Nat := rev + amount
def pegStabilityModule_sellStable := sell
def pegStabilityModule_buyStable := buy
def pegStabilityModule_schedulePolicy (feeBps ceiling : Nat) : Nat × Nat := (feeBps, ceiling)
def pegStabilityModule_applyPolicy (p : Psm) (feeBps ceiling : Nat) : Psm :=
  { p with feeBps := feeBps, ceiling := ceiling }
def pegStabilityModule_info (p : Psm) : Int × Nat × Nat :=
  (p.stableDebt, p.feeBps, p.ceiling)
def pegStabilityModule_debt (p : Psm) : Int := p.stableDebt

end Rholphin.Model.Psm
