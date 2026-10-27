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
