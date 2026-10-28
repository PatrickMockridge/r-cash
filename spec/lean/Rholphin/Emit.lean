import Rholphin.Arith.Div
import Rholphin.Arith.Issuer
import Rholphin.Arith.Savings
import Rholphin.Arith.Psm
import Rholphin.Arith.Amm
import Rholphin.Model.Issuer
import Rholphin.Model.BufferSavings
import Rholphin.Model.Psm
import Rholphin.Model.Market
import Rholphin.Model.Registry

/-!
# Vector emission

`lake env lean Rholphin/Emit.lean` prints deterministic, line-oriented vectors
consumed by `tools/gen_vectors.py`, Python model tests and Rust tests.

Format: `name|input,...|output` with decimal integers. No whitespace, no floats.
-/

namespace Rholphin.Emit

open Rholphin

def emit (name : String) (inputs : List Nat) (out : Nat) : IO Unit :=
  IO.println s!"{name}|{String.intercalate "," (inputs.map toString)}|{out}"

def emitInt (name : String) (inputs : List Nat) (out : Int) : IO Unit :=
  IO.println s!"{name}|{String.intercalate "," (inputs.map toString)}|{out}"

def emitLedger (name : String) (l : Ledger) : IO Unit :=
  IO.println s!"{name}|0|{l.supply},{l.totalPrincipal},{l.totalDebt},{l.totalAccruedInterest},{l.sin},{l.psmDebt},{l.badDebt}"

def healthB (c d r m : Nat) : Nat :=
  if d = 0 then 1
  else if r = 0 then 0
  else if (c * r / E8) * Bps ≥ d * m then 1 else 0

def main : IO Unit := do
  emit "ceilDiv.10.3" [10, 3] (ceilDiv 10 3)
  emit "ceilDiv.0.3" [0, 3] (ceilDiv 0 3)
  emit "ceilDiv.5.1" [5, 1] (ceilDiv 5 1)
  emit "ceilDiv.100000000.3" [100000000, 3] (ceilDiv 100000000 3)
  emit "floorDiv.10.3" [10, 3] (floorDiv 10 3)
  emit "floorDiv.100000000.3" [100000000, 3] (floorDiv 100000000 3)

  emit "accrue.1e6.0.12.3171" [1000000, 0, 12, 3171]
    (accrue 1000000 0 12 3171)
  emit "accrue.zeroDebt" [0, 10, 20, 3171] (accrue 0 10 20 3171)
  emit "accrue.sameHeight" [1000, 10, 10, 3171] (accrue 1000 10 10 3171)
  emit "accrue.zeroRate" [1000, 10, 20, 0] (accrue 1000 10 20 0)

  emit "health.healthy" [8000000, 100000000, 7500000000, 20000]
    (healthB 8000000 100000000 7500000000 20000)
  emit "health.unhealthy" [1000000, 100000000, 7500000000, 20000]
    (healthB 1000000 100000000 7500000000 20000)
  emit "health.zeroDebt" [0, 0, 0, 20000] (healthB 0 0 0 20000)
  emit "health.zeroRate" [1000000, 1, 0, 20000] (healthB 1000000 1 0 20000)

  emit "closeMax" [1000000, 5000] (closeMax 1000000 5000)
  emit "payout" [1000000, 800, 5000000] (payout 1000000 800 5000000)
  emit "payout.zeroRate" [1000000, 800, 0] (payout 1000000 800 0)

  emit "savings.shares.genesis" [100000000, 0, 0] (sharesFor 100000000 0 0)
  emit "savings.shares.proRata" [100000000, 100000000, 200000000]
    (sharesFor 100000000 100000000 200000000)
  emit "savings.value" [200000000, 100000000, 50000000]
    (valueOf 200000000 100000000 50000000)

  emit "psm.buyGross" [1000000, 7500000000] (buyGross 1000000 7500000000)
  emit "psm.fee" [75000000, 10] (feeCeil 75000000 10)
  emit "psm.buyOut" [1000000, 7500000000, 10] (buyOut 1000000 7500000000 10)
  emit "psm.sellGross" [100000000, 7500000000] (sellGross 100000000 7500000000)
  emit "psm.sellOut" [100000000, 7500000000, 10] (sellOut 100000000 7500000000 10)

  emit "amm.value" [100000000, 200000000, 7500000000]
    (value 100000000 200000000 7500000000)
  emit "amm.weight" [100000000, 200000000, 7500000000]
    (weight 100000000 200000000 7500000000)
  emit "amm.fee" [4000, 20, 80] (fee 4000 20 80)
  emit "amm.outB2Q" [1000000, 7500000000, 20] (outB2Q 1000000 7500000000 20)
  emit "amm.outQ2B" [1000000, 7500000000, 20] (outQ2B 1000000 7500000000 20)
  emit "amm.firstShares" [200000000] (lpSharesFirst 200000000)
  emit "amm.laterShares" [100000000, 100000000, 200000000]
    (lpSharesLater 100000000 100000000 200000000)

  let base : Ledger :=
    { totalPrincipal := 100000000, supply := 100000000, totalDebt := 100000000,
      totalAccruedInterest := 0, sin := 0, psmDebt := 0, badDebt := 0 }
  emitLedger "ledger.mint" (Model.Issuer.mint base 1000000 1000030 1000000)
  emitLedger "ledger.repay"
    (Model.Issuer.repay base 500000 30000 470000 0 1000030 1000000)
  emitLedger "ledger.liquidate" (Model.Issuer.liquidate base 500000 1000030 1000000)
  emitLedger "ledger.writeOff" (Model.Issuer.writeOff base 1000030 1000030 1000000 0)
  emitLedger "ledger.psmBuy" (Model.Issuer.psmBuy base 25000000)
  emitLedger "ledger.psmSell" (Model.Issuer.psmSell base 25000000)
  emitLedger "ledger.cover0" (Model.Issuer.cover0 base 10000000)

  let buffer : Buffer := { surplus := 100, sin := 50, savingsShareBps := 5000 }
  let covered := Model.BufferSavings.cover buffer 20
  let cancelled := buffer.surplus - covered.surplus
  emit "buffer.cover.cancelled" [100, 50, 20] cancelled
  emit "buffer.cover.surplus" [100, 50, 20] covered.surplus
  emit "buffer.cover.sin" [100, 50, 20] covered.sin

  let psm : Psm := { stableDebt := 0, ceiling := 1000, feeBps := 10, maxSupply := 10000 }
  emitInt "psm.state.buy" [250] (Model.Psm.buy psm 250).stableDebt
  emitInt "psm.state.sell" [250] (Model.Psm.sell psm 250).stableDebt

  let empty : Model.Market.Index := ⟨[], [], []⟩
  let staged := Model.Market.marketIndex_stage empty 1 1 2 3 none
  emit "market.stage.ok" [1] (if staged.isSome then 1 else 0)
  let activeMarket : Model.Market.Market := ⟨.active, 1, 2, 3⟩
  let pausedIndex : Model.Market.Index := ⟨[(1, activeMarket)], [], []⟩
  let paused := Model.Market.marketIndex_pauseAsset pausedIndex 2
  emit "market.pause.status" [1]
    (match Model.Market.lookupMarket paused.markets 1 with
     | some m => if m.status = .paused then 1 else 0
     | none => 0)
  emit "registry.external.kind" [1]
    (match (Model.Registry.Entry.external 7).kind with
     | .external => 1
     | .stablecoin => 0)

#eval main
