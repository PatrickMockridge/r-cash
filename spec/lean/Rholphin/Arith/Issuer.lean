import Rholphin.Arith.Div

/-!
# Issuer arithmetic

The formulas are copied from `CollateralMath` and the issuer arms:

* `accrue`       — per-block interest, rounded up (`debt * rate * Δh / 1e12`);
* `health`       — collateral value covers `debt * mcrBps / 10000`;
* `closeMax`     — liquidation bound, rounded up;
* `payout`       — collateral seized for a repayment, including the bonus.

Every theorem is stated for the guard the contract enforces.  Where the
contract would divide by zero, the theorem carries `0 < rate`.
-/

namespace Rholphin

/-- Per-block interest, rounded up.  Constant when no interest is due. -/
def accrue (debt last now rate : Nat) : Nat :=
  if debt = 0 ∨ now ≤ last ∨ rate = 0 then debt
  else debt + ceilDiv (debt * rate * (now - last)) E12

/-- No interest is ever removed. -/
theorem accrue_ge (debt last now rate : Nat) : debt ≤ accrue debt last now rate := by
  unfold accrue
  split
  · exact Nat.le_refl _
  · exact Nat.le_add_right debt _

/-- Accrual is monotone in the ending height. -/
theorem accrue_mono_height {debt last now₁ now₂ rate : Nat}
    (h₁ : last ≤ now₁) (h₂ : now₁ ≤ now₂) :
    accrue debt last now₁ rate ≤ accrue debt last now₂ rate := by
  unfold accrue
  by_cases hzero : debt = 0 ∨ now₁ ≤ last ∨ rate = 0
  · rw [if_pos hzero]
    split
    · exact Nat.le_refl _
    · exact Nat.le_add_right debt _
  · have hzero₂ : ¬ (debt = 0 ∨ now₂ ≤ last ∨ rate = 0) := by
      intro h
      rcases h with h | h | h
      · exact hzero (Or.inl h)
      · exact hzero (Or.inr (Or.inl (Nat.le_trans h₂ h)))
      · exact hzero (Or.inr (Or.inr h))
    rw [if_neg hzero, if_neg hzero₂]
    apply Nat.add_le_add_left
    apply ceilDiv_mono (d := E12) (by decide)
    exact Nat.mul_le_mul_left (debt * rate) (Nat.sub_le_sub_right h₂ last)

/-- The health predicate used by mint and withdraw. -/
def health (collateral debt rate mcrBps : Nat) : Prop :=
  debt = 0 ∨ (0 < rate ∧ (collateral * rate / E8) * Bps ≥ debt * mcrBps)

theorem health_zero_debt (collateral rate mcrBps : Nat) :
    health collateral 0 rate mcrBps := Or.inl rfl

/-- The close-factor ceiling: `ceil(accrued * closeFactorBps / 10000)`. -/
def closeMax (accrued closeFactorBps : Nat) : Nat :=
  ceilDiv (accrued * closeFactorBps) Bps

/-- A repayment within the close factor is within `accrued * closeFactor` plus
the rounding slack. -/
theorem close_factor_bound {accrued closeFactorBps amount : Nat}
    (h : amount ≤ closeMax accrued closeFactorBps) :
    amount * Bps ≤ accrued * closeFactorBps + (Bps - 1) := by
  unfold closeMax ceilDiv at h
  have := (Nat.le_div_iff_mul_le (k := Bps) (x := amount)
            (y := accrued * closeFactorBps + Bps - 1) (by decide)).mp h
  simpa using this

/-- Collateral seized for repaying `amount`, including the liquidation bonus. -/
def payout (amount bonusBps rate : Nat) : Nat :=
  if rate = 0 then 0 else amount * (Bps + bonusBps) * E8 / (rate * Bps)

theorem payout_zero_rate (amount bonusBps : Nat) : payout amount bonusBps 0 = 0 := by
  unfold payout
  rw [if_pos rfl]

/-- The seized amount obeys the division bound used by the solvency check. -/
theorem payout_mul_le {amount bonusBps rate : Nat} (hrate : 0 < rate) :
    payout amount bonusBps rate * (rate * Bps)
      ≤ amount * (Bps + bonusBps) * E8 := by
  unfold payout
  rw [if_neg (Nat.ne_of_gt hrate)]
  simpa [Nat.mul_comm, Nat.mul_left_comm, Nat.mul_assoc] using
    (Nat.div_mul_le_self (amount * (Bps + bonusBps) * E8) (rate * Bps))

end Rholphin
