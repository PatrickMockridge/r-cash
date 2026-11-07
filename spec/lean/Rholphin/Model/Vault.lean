import Rholphin.Model.Issuer
import Rholphin.Arith.Issuer

/-!
# Vault book transitions

The book stores one `Vault` per owner and the totals.  S2 is proved by a sum
lemma per field and transition; S4 is the health guard restated as a
preservation theorem; S6 is the write-off delta, proved on the ledger in
`Model.Issuer`.

Every arithmetic side condition is explicit: `d ≤ accrued` when a transition
moves the stored debt to the accrued debt, and `seized ≤ collateral` when the
write-off clears a vault.
-/

namespace Rholphin.Model.Vault

open Rholphin

/-- The vault field of one owner, pushed through an `if`.  The two branches are
functions of the owner, which is how a per-owner update is written. -/
theorem debt_ite (target : Owner) (g₁ g₂ : Owner → Vault) :
    (fun o => (if o = target then g₁ o else g₂ o).debt)
      = (fun o => if o = target then (g₁ o).debt else (g₂ o).debt) := by
  funext o
  by_cases h : o = target <;> simp [h]

theorem collateral_ite (target : Owner) (g₁ g₂ : Owner → Vault) :
    (fun o => (if o = target then g₁ o else g₂ o).collateral)
      = (fun o => if o = target then (g₁ o).collateral else (g₂ o).collateral) := by
  funext o
  by_cases h : o = target <;> simp [h]

/-- One owner's debt is at most the sum.  This is the side condition that
makes the `Nat` subtraction in the totals lemma total. -/
theorem le_sumDebt (b : Book) (target : Owner) :
    (b.vaults target).debt ≤ sumOwner (fun o => (b.vaults o).debt) := by
  cases target <;> simp [sumOwner] <;> omega

theorem le_sumCollateral (b : Book) (target : Owner) :
    (b.vaults target).collateral ≤ sumOwner (fun o => (b.vaults o).collateral) := by
  cases target <;> simp [sumOwner] <;> omega

/-! ## Per-owner vault transformers -/

def depositVault (v : Vault) (amount accrued : Nat) : Vault :=
  { collateral := v.collateral + amount, debt := accrued, lastHeight := v.lastHeight }

def mintVault (v : Vault) (amount accrued : Nat) : Vault :=
  { collateral := v.collateral, debt := accrued + amount, lastHeight := v.lastHeight }

def withdrawVault (v : Vault) (amount accrued : Nat) : Vault :=
  { collateral := v.collateral - amount, debt := accrued, lastHeight := v.lastHeight }

def liquidateVault (v : Vault) (amount seized accrued : Nat) : Vault :=
  { collateral := v.collateral - seized, debt := accrued - amount, lastHeight := v.lastHeight }

def writeOffVault (v : Vault) : Vault :=
  { collateral := 0, debt := 0, lastHeight := v.lastHeight }

/-! ## Collateral deposit -/

def deposit (b : Book) (target : Owner) (amount accrued : Nat) : Book :=
  { vaults := fun o => if o = target then depositVault (b.vaults o) amount accrued else b.vaults o
    totalDebt := b.totalDebt + (accrued - (b.vaults target).debt)
    totalCollateral := b.totalCollateral + amount
    totalAccruedInterest := b.totalAccruedInterest + (accrued - (b.vaults target).debt)
    badDebt := b.badDebt }

@[simp] theorem deposit_totalDebt (b : Book) (target : Owner) (amount accrued : Nat) :
    (deposit b target amount accrued).totalDebt
      = b.totalDebt + (accrued - (b.vaults target).debt) := rfl

@[simp] theorem deposit_totalCollateral (b : Book) (target : Owner) (amount accrued : Nat) :
    (deposit b target amount accrued).totalCollateral = b.totalCollateral + amount := rfl

theorem deposit_sumDebt (b : Book) (target : Owner) (amount accrued : Nat) :
    (deposit b target amount accrued).sumDebt
      = sumOwner (fun o => (b.vaults o).debt) - (b.vaults target).debt + accrued := by
  dsimp only [deposit, Book.sumDebt]
  rw [debt_ite, sumOwner_update_fn]
  simp [depositVault]

theorem deposit_sumCollateral (b : Book) (target : Owner) (amount accrued : Nat) :
    (deposit b target amount accrued).sumCollateral
      = sumOwner (fun o => (b.vaults o).collateral) + amount := by
  dsimp only [deposit, Book.sumCollateral]
  rw [collateral_ite, sumOwner_update_fn]
  have hle := le_sumCollateral b target
  simp [depositVault]
  omega

theorem deposit_S2 {b : Book} {target : Owner} {amount accrued : Nat}
    (h : S2 b) (hmono : (b.vaults target).debt ≤ accrued) :
    S2 (deposit b target amount accrued) := by
  rcases h with ⟨hdebt, hcoll⟩
  constructor
  · rw [deposit_totalDebt, deposit_sumDebt]
    rw [Book.sumDebt] at hdebt
    have hleD := le_sumDebt b target
    omega
  · rw [deposit_totalCollateral, deposit_sumCollateral]
    rw [Book.sumCollateral] at hcoll
    omega

/-! ## Mint -/

def mint (b : Book) (target : Owner) (amount accrued : Nat) : Book :=
  { vaults := fun o => if o = target then mintVault (b.vaults o) amount accrued else b.vaults o
    totalDebt := b.totalDebt + (accrued - (b.vaults target).debt) + amount
    totalCollateral := b.totalCollateral
    totalAccruedInterest := b.totalAccruedInterest + (accrued - (b.vaults target).debt)
    badDebt := b.badDebt }

@[simp] theorem mint_totalDebt (b : Book) (target : Owner) (amount accrued : Nat) :
    (mint b target amount accrued).totalDebt
      = b.totalDebt + (accrued - (b.vaults target).debt) + amount := rfl

@[simp] theorem mint_totalCollateral (b : Book) (target : Owner) (amount accrued : Nat) :
    (mint b target amount accrued).totalCollateral = b.totalCollateral := rfl

theorem mint_sumDebt (b : Book) (target : Owner) (amount accrued : Nat) :
    (mint b target amount accrued).sumDebt
      = sumOwner (fun o => (b.vaults o).debt) - (b.vaults target).debt
        + (accrued + amount) := by
  dsimp only [mint, Book.sumDebt]
  rw [debt_ite, sumOwner_update_fn]
  have hle := le_sumDebt b target
  simp [mintVault]

theorem mint_sumCollateral (b : Book) (target : Owner) (amount accrued : Nat) :
    (mint b target amount accrued).sumCollateral
      = sumOwner (fun o => (b.vaults o).collateral) := by
  dsimp only [mint, Book.sumCollateral]
  rw [collateral_ite, sumOwner_update_fn]
  have hle := le_sumCollateral b target
  simp [mintVault]
  omega

theorem mint_S2 {b : Book} {target : Owner} {amount accrued : Nat}
    (h : S2 b) (hmono : (b.vaults target).debt ≤ accrued) :
    S2 (mint b target amount accrued) := by
  rcases h with ⟨hdebt, hcoll⟩
  constructor
  · rw [mint_totalDebt, mint_sumDebt]
    rw [Book.sumDebt] at hdebt
    have hleD := le_sumDebt b target
    omega
  · rw [mint_totalCollateral, mint_sumCollateral]
    rw [Book.sumCollateral] at hcoll
    omega

/-! ## Withdraw -/

def withdraw (b : Book) (target : Owner) (amount accrued : Nat) : Book :=
  { vaults := fun o => if o = target then withdrawVault (b.vaults o) amount accrued else b.vaults o
    totalDebt := b.totalDebt + (accrued - (b.vaults target).debt)
    totalCollateral := b.totalCollateral - amount
    totalAccruedInterest := b.totalAccruedInterest + (accrued - (b.vaults target).debt)
    badDebt := b.badDebt }

@[simp] theorem withdraw_totalDebt (b : Book) (target : Owner) (amount accrued : Nat) :
    (withdraw b target amount accrued).totalDebt
      = b.totalDebt + (accrued - (b.vaults target).debt) := rfl

@[simp] theorem withdraw_totalCollateral (b : Book) (target : Owner) (amount accrued : Nat) :
    (withdraw b target amount accrued).totalCollateral = b.totalCollateral - amount := rfl

theorem withdraw_sumDebt (b : Book) (target : Owner) (amount accrued : Nat) :
    (withdraw b target amount accrued).sumDebt
      = sumOwner (fun o => (b.vaults o).debt) - (b.vaults target).debt + accrued := by
  dsimp only [withdraw, Book.sumDebt]
  rw [debt_ite, sumOwner_update_fn]
  simp [withdrawVault]

theorem withdraw_sumCollateral (b : Book) (target : Owner) (amount accrued : Nat)
    (hamount : amount ≤ (b.vaults target).collateral) :
    (withdraw b target amount accrued).sumCollateral
      = sumOwner (fun o => (b.vaults o).collateral) - amount := by
  dsimp only [withdraw, Book.sumCollateral]
  rw [collateral_ite, sumOwner_update_fn]
  have hle := le_sumCollateral b target
  simp [withdrawVault]
  omega

theorem withdraw_S2 {b : Book} {target : Owner} {amount accrued : Nat}
    (h : S2 b) (hmono : (b.vaults target).debt ≤ accrued)
    (hcoll : amount ≤ (b.vaults target).collateral) :
    S2 (withdraw b target amount accrued) := by
  rcases h with ⟨hdebt, hcollTotal⟩
  constructor
  · rw [withdraw_totalDebt, withdraw_sumDebt]
    rw [Book.sumDebt] at hdebt
    have hleD := le_sumDebt b target
    omega
  · rw [withdraw_totalCollateral, withdraw_sumCollateral b target amount accrued hcoll]
    rw [Book.sumCollateral] at hcollTotal
    omega

/-! ## Liquidation without write-off -/

def liquidate (b : Book) (target : Owner) (amount seized accrued : Nat) : Book :=
  { vaults := fun o =>
      if o = target then liquidateVault (b.vaults o) amount seized accrued else b.vaults o
    totalDebt := b.totalDebt + (accrued - (b.vaults target).debt) - amount
    totalCollateral := b.totalCollateral - seized
    totalAccruedInterest := b.totalAccruedInterest + (accrued - (b.vaults target).debt)
    badDebt := b.badDebt }

@[simp] theorem liquidate_totalDebt (b : Book) (target : Owner) (amount seized accrued : Nat) :
    (liquidate b target amount seized accrued).totalDebt
      = b.totalDebt + (accrued - (b.vaults target).debt) - amount := rfl

@[simp] theorem liquidate_totalCollateral (b : Book) (target : Owner) (amount seized accrued : Nat) :
    (liquidate b target amount seized accrued).totalCollateral
      = b.totalCollateral - seized := rfl

theorem liquidate_sumDebt (b : Book) (target : Owner) (amount seized accrued : Nat) :
    (liquidate b target amount seized accrued).sumDebt
      = sumOwner (fun o => (b.vaults o).debt) - (b.vaults target).debt
        + (accrued - amount) := by
  dsimp only [liquidate, Book.sumDebt]
  rw [debt_ite, sumOwner_update_fn]
  have hle := le_sumDebt b target
  simp [liquidateVault]

theorem liquidate_sumCollateral (b : Book) (target : Owner) (amount seized accrued : Nat)
    (hseized : seized ≤ (b.vaults target).collateral) :
    (liquidate b target amount seized accrued).sumCollateral
      = sumOwner (fun o => (b.vaults o).collateral) - seized := by
  dsimp only [liquidate, Book.sumCollateral]
  rw [collateral_ite, sumOwner_update_fn]
  have hle := le_sumCollateral b target
  simp [liquidateVault]
  omega

theorem liquidate_S2 {b : Book} {target : Owner} {amount seized accrued : Nat}
    (h : S2 b) (hmono : (b.vaults target).debt ≤ accrued)
    (hamount : amount ≤ accrued)
    (hseized : seized ≤ (b.vaults target).collateral) :
    S2 (liquidate b target amount seized accrued) := by
  rcases h with ⟨hdebt, hcoll⟩
  constructor
  · rw [liquidate_totalDebt, liquidate_sumDebt]
    rw [Book.sumDebt] at hdebt
    have hleD := le_sumDebt b target
    omega
  · rw [liquidate_totalCollateral, liquidate_sumCollateral b target amount seized accrued hseized]
    rw [Book.sumCollateral] at hcoll
    omega

/-! ## Write-off -/

def writeOff (b : Book) (target : Owner) (seized accrued : Nat) : Book :=
  { vaults := fun o => if o = target then writeOffVault (b.vaults o) else b.vaults o
    totalDebt := b.totalDebt - (b.vaults target).debt
    totalCollateral := b.totalCollateral - seized
    totalAccruedInterest := b.totalAccruedInterest + (accrued - (b.vaults target).debt)
    badDebt := b.badDebt + (accrued - seized) }

@[simp] theorem writeOff_totalDebt (b : Book) (target : Owner) (seized accrued : Nat) :
    (writeOff b target seized accrued).totalDebt
      = b.totalDebt - (b.vaults target).debt := rfl

@[simp] theorem writeOff_totalCollateral (b : Book) (target : Owner) (seized accrued : Nat) :
    (writeOff b target seized accrued).totalCollateral = b.totalCollateral - seized := rfl

theorem writeOff_sumDebt (b : Book) (target : Owner) (seized accrued : Nat) :
    (writeOff b target seized accrued).sumDebt
      = sumOwner (fun o => (b.vaults o).debt) - (b.vaults target).debt := by
  dsimp only [writeOff, Book.sumDebt]
  rw [debt_ite, sumOwner_update_fn]
  simp [writeOffVault]

theorem writeOff_sumCollateral (b : Book) (target : Owner) (seized accrued : Nat) :
    (writeOff b target seized accrued).sumCollateral
      = sumOwner (fun o => (b.vaults o).collateral) - (b.vaults target).collateral := by
  dsimp only [writeOff, Book.sumCollateral]
  rw [collateral_ite, sumOwner_update_fn]
  have hle := le_sumCollateral b target
  simp [writeOffVault]

theorem writeOff_S2 {b : Book} {target : Owner} {seized accrued : Nat}
    (h : S2 b) (hseized : seized = (b.vaults target).collateral) :
    S2 (writeOff b target seized accrued) := by
  rcases h with ⟨hdebt, hcoll⟩
  constructor
  · rw [writeOff_totalDebt, writeOff_sumDebt]
    rw [Book.sumDebt] at hdebt
    have hleD := le_sumDebt b target
    omega
  · rw [writeOff_totalCollateral, writeOff_sumCollateral]
    rw [Book.sumCollateral] at hcoll
    omega

/-! ## Health preservation (S4) -/

theorem mint_preserves_health {b : Book} {target : Owner} {amount accrued rate mcrBps : Nat}
    (hguard : health ((b.vaults target).collateral) (accrued + amount) rate mcrBps) :
    health ((mint b target amount accrued).vaults target).collateral
      ((mint b target amount accrued).vaults target).debt rate mcrBps := by
  simpa [mint, mintVault] using hguard

theorem withdraw_preserves_health {b : Book} {target : Owner} {amount accrued rate mcrBps : Nat}
    (hguard : health ((b.vaults target).collateral - amount) accrued rate mcrBps) :
    health ((withdraw b target amount accrued).vaults target).collateral
      ((withdraw b target amount accrued).vaults target).debt rate mcrBps := by
  simpa [withdraw, withdrawVault] using hguard

/-- Decidable form of health, used by the checked transitions. -/
def healthOk (collateral debt rate mcrBps : Nat) : Bool :=
  decide (debt = 0 ∨ (0 < rate ∧ (collateral * rate / E8) * Bps ≥ debt * mcrBps))

/-- Mint is accepted only when the post-state is healthy. -/
def mintChecked (b : Book) (target : Owner) (amount accrued rate mcrBps : Nat) : Option Book :=
  if healthOk (b.vaults target).collateral (accrued + amount) rate mcrBps then
    some (mint b target amount accrued)
  else none

theorem mintChecked_refuses_unhealthy {b : Book} {target : Owner}
    {amount accrued rate mcrBps : Nat}
    (h : ¬ health (b.vaults target).collateral (accrued + amount) rate mcrBps) :
    mintChecked b target amount accrued rate mcrBps = none := by
  unfold mintChecked
  have hok : healthOk (b.vaults target).collateral (accrued + amount) rate mcrBps = false := by
    unfold healthOk
    exact decide_eq_false (by simpa [health] using h)
  simp [hok]

theorem mintChecked_preserves_health {b b' : Book} {target : Owner}
    {amount accrued rate mcrBps : Nat}
    (h : mintChecked b target amount accrued rate mcrBps = some b') :
    health (b'.vaults target).collateral (b'.vaults target).debt rate mcrBps := by
  unfold mintChecked at h
  split at h
  · rename_i hok
    have hdec : decide ((accrued + amount = 0) ∨
        (0 < rate ∧ ((b.vaults target).collateral * rate / E8) * Bps ≥ (accrued + amount) * mcrBps)) = true := by
      simpa [healthOk, health] using hok
    have hg : health (b.vaults target).collateral (accrued + amount) rate mcrBps := by
      simpa [health] using of_decide_eq_true hdec
    injection h with heq
    subst heq
    simpa [mint, mintVault] using hg
  · contradiction

/-- Collateral withdrawal is accepted only when the post-state is healthy. -/
def withdrawChecked (b : Book) (target : Owner) (amount accrued rate mcrBps : Nat) : Option Book :=
  if healthOk ((b.vaults target).collateral - amount) accrued rate mcrBps then
    some (withdraw b target amount accrued)
  else none

theorem withdrawChecked_refuses_unhealthy {b : Book} {target : Owner}
    {amount accrued rate mcrBps : Nat}
    (h : ¬ health ((b.vaults target).collateral - amount) accrued rate mcrBps) :
    withdrawChecked b target amount accrued rate mcrBps = none := by
  unfold withdrawChecked
  have hok : healthOk ((b.vaults target).collateral - amount) accrued rate mcrBps = false := by
    unfold healthOk
    exact decide_eq_false (by simpa [health] using h)
  simp [hok]

theorem withdrawChecked_preserves_health {b b' : Book} {target : Owner}
    {amount accrued rate mcrBps : Nat}
    (h : withdrawChecked b target amount accrued rate mcrBps = some b') :
    health (b'.vaults target).collateral (b'.vaults target).debt rate mcrBps := by
  unfold withdrawChecked at h
  split at h
  · rename_i hok
    have hdec : decide ((accrued = 0) ∨
        (0 < rate ∧ (((b.vaults target).collateral - amount) * rate / E8) * Bps ≥ accrued * mcrBps)) = true := by
      simpa [healthOk, health] using hok
    have hg : health ((b.vaults target).collateral - amount) accrued rate mcrBps := by
      simpa [health] using of_decide_eq_true hdec
    injection h with heq
    subst heq
    simpa [withdraw, withdrawVault] using hg
  · contradiction

/-! ## Arm-level surface -/

def vaultBook_open (b : Book) (target : Owner) (height : Nat) : Book :=
  { b with vaults := fun o => if o = target then emptyVault height else b.vaults o }

/-- Rotating the vault capability is access control only: the ledger is
unchanged. The auth lives in the contract closure, not in `Vault`. -/
def vaultBook_rotate (b : Book) (_target : Owner) (_auth _newAuth : Nat) : Book := b

def vaultBook_deposit := deposit
def vaultBook_mint := mint
def vaultBook_withdraw := withdraw
def vaultBook_liquidate := liquidate

def vaultBook_repay (b : Book) (target : Owner) (amount interestPaid accrued : Nat) : Book :=
  { vaults := fun o =>
      if o = target then { b.vaults o with debt := accrued - amount } else b.vaults o
    totalDebt := b.totalDebt + (accrued - (b.vaults target).debt) - amount
    totalCollateral := b.totalCollateral
    totalAccruedInterest :=
      b.totalAccruedInterest + (accrued - (b.vaults target).debt) - interestPaid
    badDebt := b.badDebt }

def vaultBook_vault (b : Book) (target : Owner) : Vault := b.vaults target
def vaultBook_vaults (_b : Book) : List Owner := [Owner.alice, Owner.bob, Owner.carol]
def vaultBook_totals (b : Book) : Nat × Nat × Nat × Nat :=
  (b.totalDebt, b.totalCollateral, b.totalAccruedInterest, b.badDebt)
def vaultBook_params (p : Model.Issuer.RiskParams) : Model.Issuer.RiskParams := p
def vaultBook_pause (b : Book) (_paused : Bool) : Book := b
def vaultBook_attest (currency paramsHash : Nat) : Nat × Nat := (currency, paramsHash)

def liquidationEngine_liquidate := liquidate
def liquidationEngine_attest (currency : Nat) : Nat := currency

/-! ## Multi-term provisioning and waterfall

The vault term owns `vaultState`, `liquidationAuth` and the per-vault auths. The
T1 issuer and T3 buffer effects arrive through provisioned facets; the T5 params
and the T1/T3/T4 reads are pinned URIs. The model below records the two
structural changes: a facet slot is write-once, and a deploy either commits the
post-state or aborts after an effect (P6). -/

/-- The five facets the vault consumer accepts. -/
inductive FacetKind where
  | mint
  | burn
  | settle
  | custody
  | buffer
  deriving DecidableEq, Repr

/-- The consumer's write-once slots, abstracted to the installed-kind set. -/
structure Slots where
  installed : FacetKind → Bool

def Slots.empty : Slots := { installed := fun _ => false }

/-- Install a facet once. A second install is refused, which is what the shop's
one-shot nonce plus this guard enforce together. -/
def Slots.install (s : Slots) (k : FacetKind) : Option Slots :=
  if s.installed k then none
  else some { installed := fun j => if j = k then true else s.installed j }

theorem install_first (s : Slots) (k : FacetKind) (h : s.installed k = false) :
    (s.install k).isSome = true := by
  unfold Slots.install
  simp [h]

theorem install_twice_refused (s : Slots) (k : FacetKind) (h : s.installed k = true) :
    s.install k = none := by
  unfold Slots.install
  simp [h]

theorem install_marks (s : Slots) (k : FacetKind) :
    ∀ s', s.install k = some s' → s'.installed k = true := by
  intro s' hinst
  unfold Slots.install at hinst
  split at hinst
  · contradiction
  · injection hinst with heq
    subst heq
    simp

/-- The consumer's `acceptFacet` transition: install the verified facet once. -/
def vaultAccept_acceptFacet (s : Slots) (k : FacetKind) : Option Slots := s.install k

/-- The external effects the waterfall may perform before committing. -/
inductive Effect where
  | mint (amount : Nat)
  | burn (amount : Nat)
  | settle (principal interest : Nat)
  | custodyDeposit (amount : Nat)
  | custodyWithdraw (amount : Nat)
  | bufferCover (badDebt : Nat)
  | bufferPaySavings
  deriving DecidableEq, Repr

/-- A deploy either commits the computed post-state or aborts. Aborting is
`fail()`: the whole deploy rolls back, including every effect above. -/
inductive DeployResult (α : Type) where
  | committed (value : α)
  | aborted
  deriving Repr

/-- Effect-then-commit: `effectOk` records the pinned callee's success and
`revalidated` records the vault-state rev/auth check after the effect. -/
def waterfall (pre post : Book) (effectOk revalidated : Bool) : DeployResult Book :=
  if effectOk && revalidated then .committed post else .aborted

theorem waterfall_abort (pre post : Book) (effectOk : Bool) :
    waterfall pre post effectOk false = .aborted := by
  simp [waterfall]

theorem waterfall_commit (pre post : Book) :
    waterfall pre post true true = .committed post := by
  simp [waterfall]

/-- A committed waterfall preserves S2 whenever the computed post-state does. -/
theorem waterfall_commit_S2 {pre post : Book} (h : S2 post) :
    ∀ r, waterfall pre post true true = .committed r → S2 r := by
  intro r hr
  rw [waterfall_commit] at hr
  injection hr with heq
  subst heq
  exact h

/-- A per-auth cell read by a facet on every call, not snapshotted. -/
structure AuthCell where
  value : Nat
  rev : Nat

def AuthCell.check (c : AuthCell) (auth : Nat) : Bool := auth == c.value

def AuthCell.rotate (c : AuthCell) (newAuth : Nat) : AuthCell :=
  { value := newAuth, rev := c.rev + 1 }

theorem rotate_old_refused (c : AuthCell) (newAuth : Nat) (h : newAuth ≠ c.value) :
    (c.rotate newAuth).check c.value = false := by
  have h' : c.value ≠ newAuth := fun he => h he.symm
  simp [AuthCell.rotate, AuthCell.check, h']

theorem rotate_new_accepted (c : AuthCell) (newAuth : Nat) :
    (c.rotate newAuth).check newAuth = true := by
  simp [AuthCell.rotate, AuthCell.check]

/-- A provisioned facet holds the cell, not a snapshot, so it stays live across
rotation while the old raw auth is refused. -/
def facetMint (c : AuthCell) (auth : Nat) : Option Nat :=
  if c.check auth then some 1 else none

theorem facet_survives_rotation (c : AuthCell) (newAuth : Nat) :
    facetMint (c.rotate newAuth) newAuth = some 1 := by
  simp [facetMint, rotate_new_accepted]

/-- Governor-authorized liquidation-auth rotation: the cell is reposted with a
fresh value, so the old auth is refused and the engine stays live. -/
def liquidationAuthLedger_rotate (c : AuthCell) (newAuth : Nat) : AuthCell :=
  c.rotate newAuth

end Rholphin.Model.Vault
