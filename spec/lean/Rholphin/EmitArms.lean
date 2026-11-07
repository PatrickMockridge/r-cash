import Rholphin.Model.Psm
import Rholphin.Model.BufferSavings
import Rholphin.Model.Vault
import Rholphin.Model.Market
import Rholphin.Crypto.Hash
import Rholphin.Crypto.Sig
import Rholphin.Crypto.Claim

/-!
# Arm-level behavioural vectors

`lake env lean Rholphin/EmitArms.lean` prints `name|inputs|output` lines for the
checked transitions and the abstract interfaces.  `tools/check_arm_vectors.py`
compares them with `tests/vectors/arms.json`.

A refusal is `-1` for an `Int`-valued arm and `0` for a success bit.  These are
model vectors: they pin the Lean semantics, not the deployed term.
-/

namespace Rholphin.EmitArms

open Rholphin

def emitInt (name : String) (inputs : List Nat) (out : Int) : IO Unit :=
  IO.println s!"{name}|{String.intercalate "," (inputs.map toString)}|{out}"

def emitNat (name : String) (inputs : List Nat) (out : Nat) : IO Unit :=
  emitInt name inputs (Int.ofNat out)

def bit (b : Bool) : Nat := if b then 1 else 0

def optBit {α : Type} : Option α → Nat
  | some _ => 1
  | none => 0

def optInt {α : Type} (f : α → Int) : Option α → Int
  | some x => f x
  | none => -1

def main : IO Unit := do
  let p0 : Psm := { stableDebt := 1000, ceiling := 5000, feeBps := 10, maxSupply := 10000 }
  let p1 : Psm := { stableDebt := 5000, ceiling := 5000, feeBps := 10, maxSupply := 10000 }
  let p2 : Psm := { stableDebt := 0, ceiling := 5000, feeBps := 10, maxSupply := 10000 }

  emitInt "psm.buy.ok" [1000, 5000, 250]
    (optInt (fun p => p.stableDebt) (Model.Psm.buyChecked p0 250))
  emitInt "psm.buy.over" [5000, 5000, 1]
    (optInt (fun p => p.stableDebt) (Model.Psm.buyChecked p1 1))
  emitInt "psm.buy.negative" [1000, 5000, 0]
    (optInt (fun p => p.stableDebt) (Model.Psm.buyChecked p0 (-1)))
  emitInt "psm.sell.ok" [1000, 10000, 250]
    (optInt (fun p => p.stableDebt) (Model.Psm.sellChecked p0 250))
  emitInt "psm.sell.belowFloor" [0, 10000, 20000]
    (optInt (fun p => p.stableDebt) (Model.Psm.sellChecked p2 20000))

  let s0 : Savings := { totalShares := 0, totalAssets := 0, shares := fun _ => 0 }
  let s1 : Savings := { totalShares := 10, totalAssets := 100, shares := fun _ => 0 }
  emitNat "savings.notify.zero" [0] (optBit (Model.BufferSavings.notifyChecked s0 5))
  emitNat "savings.notify.ok" [10] (optBit (Model.BufferSavings.notifyChecked s1 5))

  let vHealthy : Vault := { collateral := 1000, debt := 0, lastHeight := 0 }
  let vThin : Vault := { collateral := 10, debt := 0, lastHeight := 0 }
  let bHealthy : Book :=
    { vaults := fun _ => vHealthy, totalDebt := 0, totalCollateral := 1000,
      totalAccruedInterest := 0, badDebt := 0 }
  let bThin : Book :=
    { vaults := fun _ => vThin, totalDebt := 0, totalCollateral := 10,
      totalAccruedInterest := 0, badDebt := 0 }
  emitInt "vault.mint.healthy" [1000, 100]
    (optInt (fun b => Int.ofNat b.totalDebt)
      (Model.Vault.mintChecked bHealthy Owner.alice 100 0 E8 20000))
  emitInt "vault.mint.unhealthy" [10, 100]
    (optInt (fun b => Int.ofNat b.totalDebt)
      (Model.Vault.mintChecked bThin Owner.alice 100 0 E8 20000))

  emitNat "market.admit.active" [1] (bit (Model.Market.tradabilityGate_admit .active true 100 1000 10 5000))
  emitNat "market.admit.draft" [1] (bit (Model.Market.tradabilityGate_admit .draft true 100 1000 10 5000))
  emitNat "market.admit.minTicket" [1] (bit (Model.Market.tradabilityGate_admit .active true 5 1000 10 5000))
  emitNat "market.admit.maxTrade" [1] (bit (Model.Market.tradabilityGate_admit .active true 10000 1000 10 5000))

  let hasher : Hasher := fun s vs => ⟨s * 1000 + vs.length⟩
  emitNat "hash.put.match" [1, 2]
    (optBit (TermsPut hasher ⟨1002⟩ 1 [2, 3]))
  emitNat "hash.put.mismatch" [1, 2]
    (optBit (TermsPut hasher ⟨999⟩ 1 [2, 3]))

  let scheme : SigScheme :=
    { verify := fun k m sig => sig.signer == k.id && sig.message == m }
  emitNat "sig.ok" [1, 42] (bit (scheme.verify ⟨1⟩ 42 ⟨1, 42⟩))
  emitNat "sig.wrongSigner" [1, 42] (bit (scheme.verify ⟨1⟩ 42 ⟨2, 42⟩))

  let claimScheme : ClaimScheme := { hash := fun secret => ⟨secret.value * 31⟩ }
  let transfer : Claim := { secretHash := ⟨7 * 31⟩, status := 0 }
  emitNat "claim.ok" [7] (optBit (claim claimScheme transfer ⟨7⟩))
  emitNat "claim.wrong" [8] (optBit (claim claimScheme transfer ⟨8⟩))

end Rholphin.EmitArms

#eval! Rholphin.EmitArms.main
