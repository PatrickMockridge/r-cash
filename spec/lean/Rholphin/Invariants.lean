import Rholphin.Model.Issuer
import Rholphin.Model.Vault
import Rholphin.Model.BufferSavings
import Rholphin.Model.Psm

/-!
# Invariant obligations

Each theorem is named for the invariant and the transition that carries it.
S1, S2, S3 and S10 are state invariants for the atomic transitions defined in
the model modules.  S9 and S12 are transition obligations: the waterfall bound
and the timelock ordering.

S4–S7 are obligations on the guards, not untimed state predicates: interest
accrual changes debt with no transition, so a stored-debt health predicate is
not preserved by time.  The health and payout lemmas live in
`Model.Vault` and `Arith.Issuer`.
-/

namespace Rholphin.Invariants

open Rholphin

/-! ## S1 — supply is the principal ledger -/

def S1_mint := @Model.Issuer.mint_S1
def S1_burn := @Model.Issuer.burn_S1
def S1_repay := @Model.Issuer.repay_S1
def S1_liquidate := @Model.Issuer.liquidate_S1
def S1_writeOff := @Model.Issuer.writeOff_S1
def S1_psmBuy := @Model.Issuer.psmBuy_S1
def S1_psmSell := @Model.Issuer.psmSell_S1
def S1_cover0 := @Model.Issuer.cover0_S1

/-! ## S2 — totals are the owner sums -/

def S2_deposit := @Model.Vault.deposit_S2
def S2_mint := @Model.Vault.mint_S2
def S2_withdraw := @Model.Vault.withdraw_S2
def S2_liquidate := @Model.Vault.liquidate_S2
def S2_writeOff := @Model.Vault.writeOff_S2

/-! ## S3 — the monetary identity -/

def S3_mint := @Model.Issuer.mint_S3
def S3_repay := @Model.Issuer.repay_S3
def S3_liquidate := @Model.Issuer.liquidate_S3
def S3_writeOff := @Model.Issuer.writeOff_S3
def S3_psmBuy := @Model.Issuer.psmBuy_S3
def S3_psmSell := @Model.Issuer.psmSell_S3
def S3_cover0 := @Model.Issuer.cover0_S3
def S3_accrual := @Model.Issuer.accrualDelta_S3

/-! ## S4–S7 — transition obligations -/

def S4_mint := @Model.Vault.mint_preserves_health
def S4_withdraw := @Model.Vault.withdraw_preserves_health
def S5_close_factor := @close_factor_bound
def S6_writeOff_badDebt := @Model.Issuer.writeOff_badDebt
def S7_settle_principal := @Model.Issuer.settle_principal
def S7_settle_S1 := @Model.Issuer.settle_S1



/-! ## S9 — the waterfall -/

def S9_cover_le := @Model.BufferSavings.cover_surplus_le
def S9_paySavings_le := @Model.BufferSavings.paySavings_le
def S9_waterfall_le := @Model.BufferSavings.waterfall_le

/-! ## S10 — savings conservation -/

def S10_deposit := @Model.BufferSavings.deposit_S10
def S10_withdraw := @Model.BufferSavings.withdraw_S10
def S10_notify := @Model.BufferSavings.notify_S10

/-! ## S11 — PSM bounds -/

def S11_buy_ceiling := @Model.Psm.buy_ceiling
def S11_sell_floor := @Model.Psm.sell_floor
def S11_sell_ceiling := @Model.Psm.sell_preserves_ceiling

/-! ## S12 — governed changes execute only after the timelock -/

structure Schedule where
  readyAt : Nat

def schedule (height timelock : Nat) : Schedule :=
  { readyAt := height + timelock }

def canExecute (s : Schedule) (height : Nat) : Prop := s.readyAt ≤ height

theorem S12_not_early (height timelock now : Nat) (h : now < height + timelock) :
    ¬ canExecute (schedule height timelock) now := by
  dsimp only [canExecute, schedule]
  omega

theorem S12_ready (height timelock : Nat) :
    canExecute (schedule height timelock) (height + timelock) := by
  dsimp only [canExecute, schedule]
  exact Nat.le_refl _

structure Gov where
  lastNonce : Nat
  timelock : Nat

def authorize (g : Gov) (nonce : Nat) : Gov :=
  if g.lastNonce < nonce then { g with lastNonce := nonce } else g

theorem S12_nonce_monotone (g : Gov) (nonce : Nat) :
    g.lastNonce ≤ (authorize g nonce).lastNonce := by
  unfold authorize
  split <;> simp_all <;> omega

end Rholphin.Invariants
