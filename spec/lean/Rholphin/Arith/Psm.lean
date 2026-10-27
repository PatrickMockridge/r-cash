import Rholphin.Arith.Issuer

/-!
# PSM arithmetic

Buying stablecoin with REV: `gross = floor(rev * rate / 1e8)`, fee rounded up,
`stableOut = gross - fee`.  Selling stablecoin for REV: `gross = floor(stable *
1e8 / rate)`, fee rounded up, `revOut = gross - fee`.

`stableDebt` is signed in the model; these lemmas bound the unsigned output.
-/

namespace Rholphin

/-- Gross stablecoin for `amount` REV at `rate` (quote per REV, 1e8). -/
def buyGross (amount rate : Nat) : Nat := amount * rate / E8

/-- Gross REV for `amount` stablecoin at `rate`. -/
def sellGross (amount rate : Nat) : Nat := amount * E8 / rate

/-- Fee in the smallest unit, rounded up. -/
def feeCeil (gross feeBps : Nat) : Nat := ceilDiv (gross * feeBps) Bps

/-- Net stablecoin minted by a buy. -/
def buyOut (amount rate feeBps : Nat) : Nat :=
  buyGross amount rate - feeCeil (buyGross amount rate) feeBps

/-- Net REV paid by a sell. -/
def sellOut (amount rate feeBps : Nat) : Nat :=
  sellGross amount rate - feeCeil (sellGross amount rate) feeBps

/-- A fee at most 10000 bps never exceeds the gross. -/
theorem fee_le_gross {gross feeBps : Nat} (h : feeBps ≤ Bps) :
    feeCeil gross feeBps ≤ gross := by
  unfold feeCeil
  exact ceilDiv_le_self (by decide) h

theorem buyOut_le_gross (amount rate feeBps : Nat) :
    buyOut amount rate feeBps ≤ buyGross amount rate :=
  Nat.sub_le _ _

theorem sellOut_le_gross (amount rate feeBps : Nat) :
    sellOut amount rate feeBps ≤ sellGross amount rate :=
  Nat.sub_le _ _

/-- Selling never returns more REV than the stablecoin is worth at the oracle
rate, by the floor division bound. -/
theorem sellGross_mul_le {amount rate : Nat} (hrate : 0 < rate) :
    sellGross amount rate * rate ≤ amount * E8 := by
  unfold sellGross
  simpa [Nat.mul_comm] using Nat.div_mul_le_self (amount * E8) rate

/-- Buying never mints more stablecoin than the REV is worth at the oracle
rate. -/
theorem buyGross_mul_le (amount rate : Nat) :
    buyGross amount rate * E8 ≤ amount * rate := by
  unfold buyGross
  simpa [Nat.mul_comm] using Nat.div_mul_le_self (amount * rate) E8

end Rholphin
