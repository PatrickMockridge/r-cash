import Rholphin.Basic

/-!
# Model types

Three owners are enough to state every sum invariant; the owner count is an
explicit abstraction, not a claim about the deployed system.  Vault and ledger
quantities are natural numbers where the contract guarantees non-negativity and
`Int` where the quantity is signed (`psmDebt`) or an intermediate delta.
-/

namespace Rholphin

inductive Owner where
  | alice
  | bob
  | carol
  deriving DecidableEq, Repr

open Owner

/-- Sum over the three abstract owners. -/
def sumOwner (f : Owner → Nat) : Nat :=
  f alice + f bob + f carol

/-- Replacing one owner's value changes the sum by that delta. -/
theorem sumOwner_update (target : Owner) (f : Owner → Nat) (v : Nat) :
    sumOwner (fun o => if o = target then v else f o)
      = sumOwner f - f target + v := by
  cases target <;> simp [sumOwner] <;> omega

/-- Pointwise replacement: the replacing value may depend on the owner. -/
theorem sumOwner_update_fn (target : Owner) (f g : Owner → Nat) :
    sumOwner (fun o => if o = target then g o else f o)
      = sumOwner f - f target + g target := by
  cases target <;> simp [sumOwner] <;> omega

structure Vault where
  collateral : Nat
  debt : Nat
  lastHeight : Nat
  deriving Repr

def emptyVault (height : Nat) : Vault :=
  { collateral := 0, debt := 0, lastHeight := height }

structure Book where
  vaults : Owner → Vault
  totalDebt : Nat
  totalCollateral : Nat
  totalAccruedInterest : Nat
  badDebt : Nat

def Book.sumDebt (b : Book) : Nat :=
  sumOwner (fun o => (b.vaults o).debt)

def Book.sumCollateral (b : Book) : Nat :=
  sumOwner (fun o => (b.vaults o).collateral)

def Book.withVault (b : Book) (target : Owner) (v : Vault) : Book :=
  { b with vaults := fun o => if o = target then v else b.vaults o }

theorem Book.withVault_sumDebt (b : Book) (target : Owner) (v : Vault) :
    (b.withVault target v).sumDebt = b.sumDebt - (b.vaults target).debt + v.debt := by
  unfold Book.withVault Book.sumDebt
  have hfun : (fun o => (if o = target then v else b.vaults o).debt)
      = (fun o => if o = target then v.debt else (b.vaults o).debt) := by
    funext o
    by_cases h : o = target <;> simp [h]
  rw [hfun, sumOwner_update]

theorem Book.withVault_sumCollateral (b : Book) (target : Owner) (v : Vault) :
    (b.withVault target v).sumCollateral
      = b.sumCollateral - (b.vaults target).collateral + v.collateral := by
  unfold Book.withVault Book.sumCollateral
  have hfun : (fun o => (if o = target then v else b.vaults o).collateral)
      = (fun o => if o = target then v.collateral else (b.vaults o).collateral) := by
    funext o
    by_cases h : o = target <;> simp [h]
  rw [hfun, sumOwner_update]

/-- S2: the totals are the sums of the vault fields. -/
def S2 (b : Book) : Prop :=
  b.totalDebt = b.sumDebt ∧ b.totalCollateral = b.sumCollateral

/-- The monetary ledger.  `psmDebt` is signed; `totalPrincipal` tracks the
stablecoin supply one-for-one. -/
structure Ledger where
  totalPrincipal : Int
  supply : Int
  totalDebt : Int
  totalAccruedInterest : Int
  sin : Int
  psmDebt : Int
  badDebt : Int

/-- S1: the supply is the principal ledger. -/
def S1 (l : Ledger) : Prop := l.supply = l.totalPrincipal

/-- S3: the monetary identity. -/
def S3 (l : Ledger) : Prop :=
  l.totalDebt + l.sin + l.psmDebt = l.supply + l.totalAccruedInterest

/-- The savings pool. -/
structure Savings where
  totalShares : Nat
  totalAssets : Nat
  shares : Owner → Nat

def Savings.sumShares (s : Savings) : Nat := sumOwner s.shares

/-- S10: shares are conserved across owners. -/
def S10 (s : Savings) : Prop := s.totalShares = s.sumShares

/-- The surplus buffer. -/
structure Buffer where
  surplus : Nat
  sin : Nat
  savingsShareBps : Nat

/-- The PSM policy and signed debt. -/
structure Psm where
  stableDebt : Int
  ceiling : Nat
  feeBps : Nat
  maxSupply : Nat

end Rholphin
