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

structure Lock where
  funded : Bool
  released : Bool
  cancelled : Bool
  untilH : Nat
  beneficiary : Nat
  funder : Nat
  shares : Nat
  minBlocks : Nat

def poolTemplate_create (base quote : Nat) : Pool × Lock :=
  ({ rb := 0, rq := 0, totalShares := 0, seeded := false },
   { funded := false, released := false, cancelled := false, untilH := 0,
     beneficiary := 0, funder := 0, shares := 0, minBlocks := base + quote })

def fxPool_pair (base quote : Nat) : Nat × Nat := (base, quote)
def fxPool_reserves (p : Pool) : Nat × Nat × Nat × Bool :=
  (p.rb, p.rq, p.totalShares, p.seeded)
def fxPool_balances (base balance quote balance' : Nat) : Nat × Nat := (balance, balance')
def fxPool_attest (p : Pool) : Pool := p

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

/-! ## Liquidity lock -/

def liquidityLock_fund (l : Lock) (now untilH shares : Nat) : Option Lock :=
  if l.funded then none
  else if untilH < now + l.minBlocks then none
  else some { l with funded := true, untilH := untilH, shares := shares }

/-- L1: a lock shorter than the market's minimum is refused. -/
theorem fund_refuses_short (l : Lock) {now untilH shares : Nat}
    (h : untilH < now + l.minBlocks) :
    liquidityLock_fund l now untilH shares = none := by
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

def liquidityLock_info (l : Lock) : Bool × Bool × Bool × Nat × Nat × Nat :=
  (l.funded, l.released, l.cancelled, l.untilH, l.beneficiary, l.shares)

end Rholphin.Model.Pool
