import Rholphin.Model.Types
import Rholphin.Arith.Savings

/-!
# Surplus buffer and savings pool

S10 is share conservation: every deposit and withdrawal moves the total and the
owner's balance by the same amount; `notify` moves no shares.  S9 is the
waterfall bound: `cover` never cancels more than the surplus, and `paySavings`
never moves more than the remaining surplus.
-/

namespace Rholphin.Model.BufferSavings

open Rholphin

theorem le_sumShares (s : Savings) (target : Owner) :
    s.shares target ≤ sumOwner s.shares := by
  cases target <;> simp [sumOwner] <;> omega

def deposit (s : Savings) (target : Owner) (amount shares : Nat) : Savings :=
  { totalShares := s.totalShares + shares
    totalAssets := s.totalAssets + amount
    shares := fun o => if o = target then s.shares o + shares else s.shares o }

theorem deposit_S10 {s : Savings} {target : Owner} {amount shares : Nat}
    (h : S10 s) : S10 (deposit s target amount shares) := by
  unfold S10 at h
  unfold S10
  dsimp only [Savings.sumShares] at h ⊢
  dsimp only [deposit]
  rw [sumOwner_update_fn]
  have hle := le_sumShares s target
  omega

def withdraw (s : Savings) (target : Owner) (shares amount : Nat) : Savings :=
  { totalShares := s.totalShares - shares
    totalAssets := s.totalAssets - amount
    shares := fun o => if o = target then s.shares o - shares else s.shares o }

theorem withdraw_S10 {s : Savings} {target : Owner} {shares amount : Nat}
    (h : S10 s) (hheld : shares ≤ s.shares target) :
    S10 (withdraw s target shares amount) := by
  unfold S10 at h
  unfold S10
  dsimp only [Savings.sumShares] at h ⊢
  dsimp only [withdraw]
  rw [sumOwner_update_fn]
  have hle := le_sumShares s target
  omega

def notify (s : Savings) (amount : Nat) : Savings :=
  { s with totalAssets := s.totalAssets + amount }

theorem notify_S10 (s : Savings) (amount : Nat) (h : S10 s) :
    S10 (notify s amount) := h

/-! ## The waterfall -/

def cover (b : Buffer) (badDebt : Nat) : Buffer :=
  let newSin := b.sin + badDebt
  let cancelled := if b.surplus ≤ newSin then b.surplus else newSin
  { b with surplus := b.surplus - cancelled, sin := newSin - cancelled }

theorem cover_surplus_le (b : Buffer) (badDebt : Nat) :
    (cover b badDebt).surplus ≤ b.surplus := by
  dsimp only [cover]
  split <;> omega

theorem cover_sin_le (b : Buffer) (badDebt : Nat) :
    (cover b badDebt).sin ≤ b.sin + badDebt := by
  dsimp only [cover]
  split <;> omega

def paySavings (b : Buffer) : Buffer :=
  { b with surplus := b.surplus - b.surplus * b.savingsShareBps / Bps }

theorem paySavings_le (b : Buffer) : (paySavings b).surplus ≤ b.surplus := by
  dsimp only [paySavings]
  exact Nat.sub_le _ _

/-- The waterfall never overspends: after `cover` and `paySavings`, the
surplus is at most what it was. -/
theorem waterfall_le (b : Buffer) (badDebt : Nat) :
    (paySavings (cover b badDebt)).surplus ≤ b.surplus :=
  Nat.le_trans (paySavings_le _) (cover_surplus_le b badDebt)

/-! ## Arm-level surface -/

def savingsPool_deposit := deposit
def savingsPool_withdraw := withdraw
def savingsPool_notify := notify
def savingsPool_info (s : Savings) : Nat × Nat := (s.totalShares, s.totalAssets)
def savingsPool_position (s : Savings) (target : Owner) : Nat := s.shares target

def surplusBuffer_deposit (b : Buffer) (amount : Nat) : Buffer :=
  { b with surplus := b.surplus + amount }
def surplusBuffer_paySavings := paySavings
def surplusBuffer_cover := cover
def surplusBuffer_info (b : Buffer) : Nat × Nat × Nat :=
  (b.surplus, b.sin, b.savingsShareBps)
def surplusBuffer_scheduleShare (bps : Nat) : Nat := bps
def surplusBuffer_applyShare (b : Buffer) (bps : Nat) : Buffer :=
  { b with savingsShareBps := bps }

end Rholphin.Model.BufferSavings
