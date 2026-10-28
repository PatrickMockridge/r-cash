import Rholphin.Model.Types

/-!
# Issuer transitions on the monetary ledger

Each definition is the net delta of one atomic transition in
`docs/spec/flows/01-issuer.yaml` and `02-vault.yaml`.  The parameters `accrued`
and `d` are the accrued debt and the stored debt before the transition; the
guards ensure `d ≤ accrued` (in `Nat` terms), but the ledger is `Int`, so the
theorems do not need the side condition.

`repay` is the composite: settle, `cover(0)`, `paySavings`, then the vault
update.  It is the only arm where the interest split matters, hence the
`principalPaid + interestPaid = amount` hypothesis.
-/

namespace Rholphin.Model.Issuer

open Rholphin

def mint (l : Ledger) (amount accrued d : Int) : Ledger :=
  { l with
    totalPrincipal := l.totalPrincipal + amount
    supply := l.supply + amount
    totalDebt := l.totalDebt + (accrued - d) + amount
    totalAccruedInterest := l.totalAccruedInterest + (accrued - d) }

theorem mint_S1 (l : Ledger) (amount accrued d : Int) (h : S1 l) :
    S1 (mint l amount accrued d) := by
  unfold S1 at *; unfold mint; simp; omega

theorem mint_S3 (l : Ledger) (amount accrued d : Int) (h : S3 l) :
    S3 (mint l amount accrued d) := by
  unfold S3 at *; unfold mint; simp; omega

def burn (l : Ledger) (amount : Int) : Ledger :=
  { l with
    totalPrincipal := l.totalPrincipal - amount
    supply := l.supply - amount }

theorem burn_S1 (l : Ledger) (amount : Int) (h : S1 l) :
    S1 (burn l amount) := by
  unfold S1 at *; unfold burn; simp; omega

/-! A standalone burn reduces supply with no debt movement, so S3 is preserved
only by the composites that burn as an effect (liquidate, repay, writeOff,
cover and PSM sell).  The theorem is intentionally absent. -/

/-- The principal side of a repayment: `settle` burns principal and deposits
interest in the buffer.  S1 holds; S3 is a composite obligation because the
interest deposit and the vault update happen in the same deploy. -/
def settle (l : Ledger) (principal interest : Int) : Ledger :=
  { l with
    totalPrincipal := l.totalPrincipal - principal
    supply := l.supply - principal }

theorem settle_S1 (l : Ledger) (principal interest : Int) (h : S1 l) :
    S1 (settle l principal interest) := by
  unfold S1 at *; unfold settle; simp; omega

theorem settle_principal (l : Ledger) (principal interest : Int) :
    (settle l principal interest).supply = l.supply - principal := rfl

/-- Interest deposited to the buffer: supply is unchanged, so S3 is unchanged. -/
def depositInterest (l : Ledger) (interest : Int) : Ledger := l

theorem depositInterest_S3 (l : Ledger) (interest : Int) (h : S3 l) :
    S3 (depositInterest l interest) := h

/-- The repay composite. -/
def repay (l : Ledger) (amount interestPaid principalPaid cancelled accrued d : Int) : Ledger :=
  { l with
    totalPrincipal := l.totalPrincipal - principalPaid - cancelled
    supply := l.supply - principalPaid - cancelled
    totalDebt := l.totalDebt + (accrued - d) - amount
    totalAccruedInterest := l.totalAccruedInterest + (accrued - d) - interestPaid
    sin := l.sin - cancelled }

theorem repay_S1 (l : Ledger) (amount interestPaid principalPaid cancelled accrued d : Int)
    (h : S1 l) : S1 (repay l amount interestPaid principalPaid cancelled accrued d) := by
  unfold S1 at *; unfold repay; simp; omega

theorem repay_S3 (l : Ledger) (amount interestPaid principalPaid cancelled accrued d : Int)
    (h : S3 l) (hsplit : principalPaid + interestPaid = amount) :
    S3 (repay l amount interestPaid principalPaid cancelled accrued d) := by
  unfold S3 at *; unfold repay; simp; omega

def liquidate (l : Ledger) (amount accrued d : Int) : Ledger :=
  { l with
    totalPrincipal := l.totalPrincipal - amount
    supply := l.supply - amount
    totalDebt := l.totalDebt + (accrued - d) - amount
    totalAccruedInterest := l.totalAccruedInterest + (accrued - d) }

theorem liquidate_S1 (l : Ledger) (amount accrued d : Int) (h : S1 l) :
    S1 (liquidate l amount accrued d) := by
  unfold S1 at *; unfold liquidate; simp; omega

theorem liquidate_S3 (l : Ledger) (amount accrued d : Int) (h : S3 l) :
    S3 (liquidate l amount accrued d) := by
  unfold S3 at *; unfold liquidate; simp; omega

/-- The write-off: burn the payment and the covered amount, clear the vault,
book the shortfall as bad debt and outstanding `sin`. -/
def writeOff (l : Ledger) (amount accrued d cancelled : Int) : Ledger :=
  { l with
    totalPrincipal := l.totalPrincipal - amount - cancelled
    supply := l.supply - amount - cancelled
    totalDebt := l.totalDebt - d
    totalAccruedInterest := l.totalAccruedInterest + (accrued - d)
    sin := l.sin + (accrued - amount) - cancelled
    badDebt := l.badDebt + (accrued - amount) }

theorem writeOff_S1 (l : Ledger) (amount accrued d cancelled : Int) (h : S1 l) :
    S1 (writeOff l amount accrued d cancelled) := by
  unfold S1 at *; unfold writeOff; simp; omega

theorem writeOff_badDebt (l : Ledger) (amount accrued d cancelled : Int) :
    (writeOff l amount accrued d cancelled).badDebt = l.badDebt + (accrued - amount) := rfl

theorem writeOff_S3 (l : Ledger) (amount accrued d cancelled : Int) (h : S3 l) :
    S3 (writeOff l amount accrued d cancelled) := by
  unfold S3 at *; unfold writeOff; simp; omega

def psmBuy (l : Ledger) (out : Int) : Ledger :=
  { l with
    totalPrincipal := l.totalPrincipal + out
    supply := l.supply + out
    psmDebt := l.psmDebt + out }

theorem psmBuy_S1 (l : Ledger) (out : Int) (h : S1 l) :
    S1 (psmBuy l out) := by
  unfold S1 at *; unfold psmBuy; simp; omega

theorem psmBuy_S3 (l : Ledger) (out : Int) (h : S3 l) :
    S3 (psmBuy l out) := by
  unfold S3 at *; unfold psmBuy; simp; omega

def psmSell (l : Ledger) (amount : Int) : Ledger :=
  { l with
    totalPrincipal := l.totalPrincipal - amount
    supply := l.supply - amount
    psmDebt := l.psmDebt - amount }

theorem psmSell_S1 (l : Ledger) (amount : Int) (h : S1 l) :
    S1 (psmSell l amount) := by
  unfold S1 at *; unfold psmSell; simp; omega

theorem psmSell_S3 (l : Ledger) (amount : Int) (h : S3 l) :
    S3 (psmSell l amount) := by
  unfold S3 at *; unfold psmSell; simp; omega

/-- `cover(0)`: cancel outstanding sin against surplus by burning both. -/
def cover0 (l : Ledger) (cancelled : Int) : Ledger :=
  { l with
    totalPrincipal := l.totalPrincipal - cancelled
    supply := l.supply - cancelled
    sin := l.sin - cancelled }

theorem cover0_S1 (l : Ledger) (cancelled : Int) (h : S1 l) :
    S1 (cover0 l cancelled) := by
  unfold S1 at *; unfold cover0; simp; omega

theorem cover0_S3 (l : Ledger) (cancelled : Int) (h : S3 l) :
    S3 (cover0 l cancelled) := by
  unfold S3 at *; unfold cover0; simp; omega

/-- Interest accrual changes the stored totals with no supply movement. -/
def accrualDelta (l : Ledger) (delta : Int) : Ledger :=
  { l with
    totalDebt := l.totalDebt + delta
    totalAccruedInterest := l.totalAccruedInterest + delta }

theorem accrualDelta_S3 (l : Ledger) (delta : Int) (h : S3 l) :
    S3 (accrualDelta l delta) := by
  unfold S3 at *; unfold accrualDelta; simp; omega

/-! ## Arm-level surface

These declarations are the per-arm names used by `docs/spec/flows`.  They are
the transition or projection named in the YAML, not stubs.
-/

structure Custody where
  rev : Nat

structure RiskParams where
  mcrBps : Nat
  bonusBps : Nat
  closeFactorBps : Nat
  ratePerBlock : Nat
  debtCeiling : Nat
  minDebt : Nat
  maxDebt : Nat
  maxOracleAge : Nat
  savingsShareBps : Nat
  psmFeeBps : Nat

def stablecoin_brand (brand : Nat) : Nat := brand
def stablecoin_issuer (issuer : Nat) : Nat := issuer
def stablecoin_supply (l : Ledger) : Int := l.totalPrincipal

/-- The issuer-side mint delta.  It preserves S1; S3 is carried by the
composite `vaultBook_mint` because the debt update is in the same deploy. -/
def stablecoin_mint (l : Ledger) (amount : Int) : Ledger :=
  { l with totalPrincipal := l.totalPrincipal + amount, supply := l.supply + amount }

def stablecoin_burn := burn

def stablecoin_settle (l : Ledger) (principal : Int) : Ledger :=
  { l with totalPrincipal := l.totalPrincipal - principal, supply := l.supply - principal }

def stablecoin_amountOf (amount : Nat) : Nat := amount
def stablecoin_attest (currency paramsHash template : Nat) : Nat × Nat × Nat :=
  (currency, paramsHash, template)

def collateralCustody_deposit (c : Custody) (amount : Nat) : Custody :=
  { c with rev := c.rev + amount }
def collateralCustody_withdraw (c : Custody) (amount : Nat) : Custody :=
  { c with rev := c.rev - amount }
def collateralCustody_balance (c : Custody) : Nat := c.rev
def collateralCustody_attest (currency : Nat) : Nat := currency

def riskParameters_params (p : RiskParams) : RiskParams := p
def riskParameters_info (p : RiskParams) (hash rev : Nat) : RiskParams × Nat × Nat :=
  (p, hash, rev)
def riskParameters_scheduleParams (pending : List (Nat × RiskParams)) (nonce : Nat)
    (p : RiskParams) : List (Nat × RiskParams) := (nonce, p) :: pending
def riskParameters_applyParams (_old : RiskParams) (args : RiskParams) : RiskParams := args
def riskParameters_attest (currency paramsHash : Nat) : Nat × Nat := (currency, paramsHash)

end Rholphin.Model.Issuer
