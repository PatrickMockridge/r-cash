import Rholphin.Arith.Div

/-!
# Savings arithmetic

`SavingsPool` holds `totalShares` and `totalAssets`; a deposit mints
`floor(amount * totalShares / totalAssets)` shares (or one share per unit at
genesis), and a withdrawal pays `floor(totalAssets * shares / totalShares)`.
`notify` raises assets with no shares, which raises every share value.
-/

namespace Rholphin

/-- Shares minted by a deposit. -/
def sharesFor (amount totalShares totalAssets : Nat) : Nat :=
  if totalShares = 0 then amount
  else if totalAssets = 0 then 0
  else amount * totalShares / totalAssets

/-- Assets paid for burning `shares`. -/
def valueOf (totalAssets totalShares shares : Nat) : Nat :=
  totalAssets * shares / totalShares

/-- The deposit does not over-mint: shares times assets never exceeds the
deposited value times the pre-existing shares. -/
theorem sharesFor_mul_le {amount totalShares totalAssets : Nat}
    (hS : 0 < totalShares) (hA : 0 < totalAssets) :
    sharesFor amount totalShares totalAssets * totalAssets ≤ amount * totalShares := by
  unfold sharesFor
  rw [if_neg (Nat.ne_of_gt hS), if_neg (Nat.ne_of_gt hA)]
  simpa [Nat.mul_comm] using
    (Nat.div_mul_le_self (amount * totalShares) totalAssets)

/-- A withdrawal pays at most the proportional assets; with `shares ≤
totalShares` it pays at most the pool. -/
theorem valueOf_mul_le {totalAssets totalShares shares : Nat} (hS : 0 < totalShares) :
    valueOf totalAssets totalShares shares * totalShares ≤ totalAssets * shares := by
  unfold valueOf
  simpa [Nat.mul_comm] using Nat.div_mul_le_self (totalAssets * shares) totalShares

theorem valueOf_le_assets {totalAssets totalShares shares : Nat}
    (hS : 0 < totalShares) (h : shares ≤ totalShares) :
    valueOf totalAssets totalShares shares ≤ totalAssets := by
  unfold valueOf
  apply Nat.div_le_of_le_mul
  calc
    totalAssets * shares ≤ totalAssets * totalShares := Nat.mul_le_mul_left totalAssets h
    _ = totalShares * totalAssets := Nat.mul_comm _ _

/-- Notifying assets never changes the share count, so the value of a share is
monotone in notified assets. -/
theorem notify_monotone {assets shares amount s : Nat} :
    valueOf assets shares s ≤ valueOf (assets + amount) shares s := by
  unfold valueOf
  apply div_le_div_of_le_left
  exact Nat.mul_le_mul_right s (Nat.le_add_right assets amount)

end Rholphin
