import Rholphin.Arith.Amm

/-!
# FX pool and liquidity lock

The pool keeps `rb`, `rq`, `totalShares` and the seed flag.  A swap changes the
reserves but never the share count (I10/I11); a remove pays a floored pro-rata
amount.  The lock is one-shot: `fund` requires `untilH >= now + minBlocks`, and
release/cancel move a funded lock to a terminal flag (I13).
-/

namespace Rholphin.Model.Pool

open Rholphin

structure Pool where
  rb : Nat
  rq : Nat
  totalShares : Nat
  seeded : Bool

/-- Native custody of the two reserves. -/
structure Custody where
  base : Nat
  quote : Nat

def PoolCustody (p : Pool) (c : Custody) : Prop := p.rb = c.base ∧ p.rq = c.quote

structure Lock where
  funded : Bool
  released : Bool
  cancelled : Bool
  untilH : Nat
  beneficiary : Nat
  funder : Nat
  shares : Nat
  minBlocks : Nat
  /-- The buyer-signed lock height (`terms.lockUntilHeight`). -/
  untilLimit : Nat
  /-- The sponsor address derived from `terms.lockBeneficiaryPubKey`. -/
  beneficiaryKey : Nat

def poolTemplate_create (base quote : Nat) : Pool × Lock :=
  ({ rb := 0, rq := 0, totalShares := 0, seeded := false },
   { funded := false, released := false, cancelled := false, untilH := 0,
     beneficiary := 0, funder := 0, shares := 0, minBlocks := base + quote,
     untilLimit := 0, beneficiaryKey := 0 })

/-- Factory creation: a fresh, empty lock for a pool's LP purse. -/
def liquidityLockFactory_create (minBlocks untilLimit beneficiaryKey : Nat) : Lock :=
  { funded := false, released := false, cancelled := false, untilH := 0,
    beneficiary := 0, funder := 0, shares := 0, minBlocks := minBlocks,
    untilLimit := untilLimit, beneficiaryKey := beneficiaryKey }

def fxPool_pair (base quote : Nat) : Nat × Nat := (base, quote)
def fxPool_reserves (p : Pool) : Nat × Nat × Nat × Bool :=
  (p.rb, p.rq, p.totalShares, p.seeded)
def fxPool_balances (base balance quote balance' : Nat) : Nat × Nat := (balance, balance')
def fxPool_attest (p : Pool) (c : Custody) : Bool :=
  decide (p.rb = c.base ∧ p.rq = c.quote)

theorem fxPool_attest_sound {p : Pool} {c : Custody} (h : fxPool_attest p c = true) :
    PoolCustody p c := by
  unfold fxPool_attest at h
  simpa [PoolCustody] using of_decide_eq_true h

def fxPool_quote (p : Pool) (baseToQuote : Bool) (dx rate feeBps : Nat) : Nat :=
  if baseToQuote then outB2Q dx rate feeBps else outQ2B dx rate feeBps

def fxPool_swap (p : Pool) (baseToQuote : Bool) (amount rate feeBps minOut : Nat) :
    Option Pool :=
  let out := if baseToQuote then outB2Q amount rate feeBps else outQ2B amount rate feeBps
  if out = 0 ∨ out < minOut then none
  else if baseToQuote then
    some { p with rb := p.rb + amount, rq := p.rq - out }
  else
    some { p with rb := p.rb - out, rq := p.rq + amount }

def fxPool_addLiquidity (p : Pool) (baseAmt quoteAmt rate minShares : Nat) : Option Pool :=
  let depositValue := value (p.rb + baseAmt) (p.rq + quoteAmt) rate
  let poolValue := value p.rb p.rq rate
  let shares := if p.seeded then lpSharesLater (depositValue - poolValue) p.totalShares poolValue
                else lpSharesFirst depositValue
  if shares = 0 ∨ shares < minShares then none
  else some { p with rb := p.rb + baseAmt, rq := p.rq + quoteAmt,
                     totalShares := p.totalShares + shares, seeded := true }

def fxPool_removeLiquidity (p : Pool) (shares minBase minQuote : Nat) : Option Pool :=
  if shares = 0 ∨ p.totalShares = 0 ∨ shares > p.totalShares then none
  else
    let baseOut := p.rb * shares / p.totalShares
    let quoteOut := p.rq * shares / p.totalShares
    if baseOut < minBase ∨ quoteOut < minQuote then none
    else some { p with rb := p.rb - baseOut, rq := p.rq - quoteOut,
                       totalShares := p.totalShares - shares,
                       seeded := p.totalShares - shares > 0 }

/-! ## Share ledger (I11) -/

/-- The share counters are a separate book; the pool updates them with the
reserve update.  This keeps the arithmetic obligation independent of the
pool's option plumbing. -/
structure ShareBook where
  totalShares : Nat
  minted : Nat
  burned : Nat

def ShareLedger (s : ShareBook) : Prop := s.totalShares + s.burned = s.minted

def ShareBook.empty : ShareBook := ⟨0, 0, 0⟩

theorem empty_ledger : ShareLedger ShareBook.empty := rfl

def mintShares (s : ShareBook) (n : Nat) : ShareBook :=
  { totalShares := s.totalShares + n, minted := s.minted + n, burned := s.burned }

theorem mintShares_preserves_ledger (s : ShareBook) (n : Nat) (h : ShareLedger s) :
    ShareLedger (mintShares s n) := by
  unfold ShareLedger at h ⊢
  dsimp only [mintShares]
  omega

def burnShares (s : ShareBook) (n : Nat) : ShareBook :=
  { totalShares := s.totalShares - n, minted := s.minted, burned := s.burned + n }

theorem burnShares_preserves_ledger (s : ShareBook) (n : Nat)
    (h : ShareLedger s) (hn : n ≤ s.totalShares) :
    ShareLedger (burnShares s n) := by
  unfold ShareLedger at h ⊢
  dsimp only [burnShares]
  omega

/-! ## Liquidity lock -/

/-- OCAP-12: the funder must be the sponsor-derived beneficiary and the lock
height must equal the term's `lockUntilHeight`. -/
def liquidityLock_fund (l : Lock) (now untilH funder beneficiary shares : Nat) : Option Lock :=
  if l.funded then none
  else if untilH ≠ l.untilLimit then none
  else if funder ≠ l.beneficiaryKey then none
  else if untilH < now + l.minBlocks then none
  else some { l with funded := true, untilH := untilH, funder := funder,
                     beneficiary := beneficiary, shares := shares }

/-- L1: a lock shorter than the market's minimum is refused. -/
theorem fund_refuses_short (l : Lock) {now untilH funder beneficiary shares : Nat}
    (h : untilH < now + l.minBlocks) :
    liquidityLock_fund l now untilH funder beneficiary shares = none := by
  unfold liquidityLock_fund
  by_cases hf : l.funded
  · simp [hf]
  · by_cases hh : untilH = l.untilLimit
    · by_cases hb : funder = l.beneficiaryKey
      · subst hh
        subst hb
        simp [hf, h]
      · simp [hf, hh, hb]
    · simp [hf, hh]

/-- OCAP-12: a funder that is not the sponsor-derived beneficiary is refused. -/
theorem fund_refuses_wrong_funder (l : Lock) {now untilH funder beneficiary shares : Nat}
    (h : funder ≠ l.beneficiaryKey) :
    liquidityLock_fund l now untilH funder beneficiary shares = none := by
  unfold liquidityLock_fund
  by_cases hf : l.funded
  · simp [hf]
  · by_cases hh : untilH = l.untilLimit
    · simp [hf, hh, h]
    · simp [hf, hh]

/-- OCAP-12: a lock height other than the signed `lockUntilHeight` is refused. -/
theorem fund_refuses_height (l : Lock) {now untilH funder beneficiary shares : Nat}
    (h : untilH ≠ l.untilLimit) :
    liquidityLock_fund l now untilH funder beneficiary shares = none := by
  unfold liquidityLock_fund
  by_cases hf : l.funded
  · simp [hf]
  · simp [hf, h]

def liquidityLock_release (l : Lock) (now : Nat) (beneficiaryOk : Nat → Bool) : Option Lock :=
  if l.funded = true ∧ l.released = false ∧ l.cancelled = false
      ∧ l.untilH ≤ now ∧ beneficiaryOk l.beneficiary = true then
    some { l with released := true }
  else none

def liquidityLock_cancel (l : Lock) (governorOk partyOk : Bool) : Option Lock :=
  if governorOk = true ∧ partyOk = true ∧ l.funded = true
      ∧ l.released = false ∧ l.cancelled = false then
    some { l with cancelled := true }
  else none

theorem fund_sets_funded {l l' : Lock} {now untilH funder beneficiary shares : Nat}
    (h : liquidityLock_fund l now untilH funder beneficiary shares = some l') :
    l'.funded = true := by
  unfold liquidityLock_fund at h
  split at h
  · contradiction
  · split at h
    · contradiction
    · split at h
      · contradiction
      · split at h
        · contradiction
        · injection h with heq
          subst heq
          rfl

theorem fund_refuses_funded {l : Lock} {now untilH funder beneficiary shares : Nat}
    (h : l.funded = true) :
    liquidityLock_fund l now untilH funder beneficiary shares = none := by
  simp [liquidityLock_fund, h]

theorem release_then_cancel_refused {l l' : Lock} {now : Nat} {beneficiaryOk : Nat → Bool}
    {governorOk partyOk : Bool}
    (h : liquidityLock_release l now beneficiaryOk = some l') :
    liquidityLock_cancel l' governorOk partyOk = none := by
  unfold liquidityLock_release at h
  split at h
  · rename_i hg
    injection h with heq
    subst heq
    simp [liquidityLock_cancel]
  · contradiction

theorem cancel_then_release_refused {l l' : Lock} {governorOk partyOk : Bool}
    {now : Nat} {beneficiaryOk : Nat → Bool}
    (h : liquidityLock_cancel l governorOk partyOk = some l') :
    liquidityLock_release l' now beneficiaryOk = none := by
  unfold liquidityLock_cancel at h
  split at h
  · rename_i hg
    injection h with heq
    subst heq
    simp [liquidityLock_release]
  · contradiction

def liquidityLock_info (l : Lock) : Bool × Bool × Bool × Nat × Nat × Nat :=
  (l.funded, l.released, l.cancelled, l.untilH, l.beneficiary, l.shares)

end Rholphin.Model.Pool
