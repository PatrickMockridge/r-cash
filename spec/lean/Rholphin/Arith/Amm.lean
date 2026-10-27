import Rholphin.Arith.Div

/-!
# AMM arithmetic

`AmmMath` is fixed-price: the oracle rate sets the value of the base reserve,
the pool weights the fee by the reserve skew, and the output is floored.  The
lemmas below are the bounds the pool arms rely on: an output never exceeds the
gross value of the input, and a first deposit cannot mint more than its value
less the locked minimum.
-/

namespace Rholphin

/-- Pool value in quote units: `floor(rb * rate / 1e8) + rq`. -/
def value (rb rq rate : Nat) : Nat := rb * rate / E8 + rq

/-- Base weight in bps: the share of value held in the base reserve. -/
def weight (rb rq rate : Nat) : Nat :=
  if value rb rq rate = 0 then Bps / 2
  else (rb * rate / E8) * Bps / value rb rq rate

/-- Fee in bps: the base spread plus a skew term. -/
def fee (weight baseSpread skewSpread : Nat) : Nat :=
  baseSpread +
    (if Bps / 2 ≤ weight then (weight - Bps / 2) * skewSpread / (Bps / 2)
     else (Bps / 2 - weight) * skewSpread / (Bps / 2))

/-- Base-to-quote output, floored twice. -/
def outB2Q (dx rate feeBps : Nat) : Nat :=
  (dx * rate / E8) * (Bps - feeBps) / Bps

/-- Quote-to-base output; zero when the rate is unusable. -/
def outQ2B (dx rate feeBps : Nat) : Nat :=
  if rate = 0 then 0 else (dx * E8 / rate) * (Bps - feeBps) / Bps

/-- The first deposit locks one unit of value. -/
def lpSharesFirst (depositValue : Nat) : Nat := depositValue - E8

/-- Later deposits receive the pro-rata share, floored. -/
def lpSharesLater (depositValue totalShares poolValue : Nat) : Nat :=
  if totalShares = 0 ∨ poolValue = 0 then 0
  else depositValue * totalShares / poolValue

/-- LP shares for a deposit. -/
def lpShares (depositValue totalShares poolValue : Nat) (first : Bool) : Nat :=
  if first then lpSharesFirst depositValue
  else lpSharesLater depositValue totalShares poolValue

/-- A fee no greater than 10000 bps keeps the output below the gross input. -/
theorem outB2Q_le (dx rate feeBps : Nat) (h : feeBps ≤ Bps) :
    outB2Q dx rate feeBps ≤ dx * rate / E8 := by
  unfold outB2Q
  apply Nat.div_le_of_le_mul
  calc
    (dx * rate / E8) * (Bps - feeBps) ≤ (dx * rate / E8) * Bps :=
      Nat.mul_le_mul_left _ (Nat.sub_le _ _)
    _ = Bps * (dx * rate / E8) := Nat.mul_comm _ _

theorem outQ2B_le (dx rate feeBps : Nat) (h : feeBps ≤ Bps) :
    outQ2B dx rate feeBps ≤ if rate = 0 then 0 else dx * E8 / rate := by
  unfold outQ2B
  split
  · exact Nat.le_refl _
  · apply Nat.div_le_of_le_mul
    calc
      (dx * E8 / rate) * (Bps - feeBps) ≤ (dx * E8 / rate) * Bps :=
        Nat.mul_le_mul_left _ (Nat.sub_le _ _)
      _ = Bps * (dx * E8 / rate) := Nat.mul_comm _ _

/-- A first deposit's shares never exceed its value. -/
theorem first_shares_le (depositValue : Nat) :
    lpSharesFirst depositValue ≤ depositValue :=
  Nat.sub_le _ _

/-- A later deposit's shares obey the floor division bound. -/
theorem later_shares_mul_le {depositValue totalShares poolValue : Nat} :
    lpSharesLater depositValue totalShares poolValue * poolValue
      ≤ depositValue * totalShares := by
  unfold lpSharesLater
  by_cases h : totalShares = 0 ∨ poolValue = 0
  · rw [if_pos h]
    simp
  · rw [if_neg h]
    simpa [Nat.mul_comm] using
      Nat.div_mul_le_self (depositValue * totalShares) poolValue

end Rholphin
