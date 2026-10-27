import Rholphin.Arith.Issuer
import Rholphin.Arith.Amm
import Rholphin.Arith.Psm

/-!
# Kernel surface

Clock, codec, verifier, bounds and the pure arithmetic contracts.  The bounds
predicates are the range checks in `02_bounds.rho`; the arithmetic wrappers are
the definitions from `Arith`.
-/

namespace Rholphin.Model.Kernel

open Rholphin

def clock_now (height : Nat) : Nat := height

def codec_canonical (schema : Nat) (values : List Nat) : List Nat :=
  schema :: values

def codec_hash (schema : Nat) (values : List Nat) : Nat :=
  values.foldl (fun acc v => acc * 31 + v) schema

def verifier_hash (bytes : List Nat) : Nat :=
  bytes.foldl (fun acc b => acc * 31 + b) 0

def verifier_sigOk (ok : Bool) : Bool := ok

def verifier_claimHash (secret : Nat) : Nat := secret

def claimCode_hash (secret : Nat) : Nat := secret

def bounds_checkIssuer (mcrBps bonusBps closeFactorBps ratePerBlock debtCeiling
    minDebt maxDebt maxOracleAge savingsShareBps psmFeeBps : Nat) : Bool :=
  decide (10000 ≤ mcrBps ∧ mcrBps ≤ 50000 ∧ bonusBps ≤ 5000
    ∧ 1 ≤ closeFactorBps ∧ closeFactorBps ≤ 10000 ∧ ratePerBlock ≤ 50000
    ∧ 10000000000 ≤ debtCeiling ∧ debtCeiling ≤ 1000000000000000
    ∧ 10000 ≤ minDebt ∧ minDebt ≤ 1000000000
    ∧ minDebt ≤ maxDebt ∧ maxDebt ≤ debtCeiling
    ∧ 1 ≤ maxOracleAge ∧ maxOracleAge ≤ 1000
    ∧ savingsShareBps ≤ 10000 ∧ psmFeeBps ≤ 1000)

def bounds_checkFeed (quorum age spread minPrice maxPrice trialBlocks
    trialMinSubmits : Nat) : Bool :=
  decide (1 ≤ quorum ∧ quorum ≤ 3 ∧ 1 ≤ age ∧ spread ≤ 10000
    ∧ 0 < minPrice ∧ minPrice ≤ maxPrice ∧ 1 ≤ trialBlocks
    ∧ quorum ≤ trialMinSubmits)

def bounds_checkPool (baseSpread skew maxTrade minLiquidity tolerance depthFloor
    minTicket : Nat) : Bool :=
  decide (baseSpread ≤ 10000 ∧ skew ≤ 10000 ∧ 1 ≤ maxTrade ∧ maxTrade ≤ 10000
    ∧ 1 ≤ minLiquidity ∧ tolerance ≤ 1000 ∧ 0 < minTicket)

def bounds_checkBook (defaultExpiry maxExpiry minAmount maxMemo maxOpId
    maxStipend : Nat) : Bool :=
  decide (1 ≤ defaultExpiry ∧ defaultExpiry ≤ maxExpiry ∧ maxExpiry ≤ 1296000
    ∧ maxMemo ≤ 4096 ∧ maxOpId ≤ 256)

def bounds_checkTransfer (amount expiry now minAmount maxExpiryBlocks : Nat) : Bool :=
  decide (minAmount ≤ amount ∧ now < expiry ∧ expiry ≤ now + maxExpiryBlocks)

def bounds_checkTerms (fields : Nat) : Bool :=
  decide (fields = 25)

def ammMath_value := value
def ammMath_weight := weight
def ammMath_fee := fee
def ammMath_out (baseToQuote : Bool) (dx rate feeBps : Nat) : Nat :=
  if baseToQuote then outB2Q dx rate feeBps else outQ2B dx rate feeBps
def ammMath_shares := lpShares
def ammMath_inputValue (base : Bool) (amount rate : Nat) : Nat :=
  if base then amount * rate / E8 else amount

def collateralMath_accrue := accrue
def collateralMath_health (collateral debt rate mcrBps : Nat) : Bool :=
  if debt = 0 then true
  else decide (0 < rate ∧ (collateral * rate / E8) * Bps ≥ debt * mcrBps)
def collateralMath_payout := payout
def collateralMath_seize := payout

end Rholphin.Model.Kernel
