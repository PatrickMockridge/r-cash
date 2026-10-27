import Rholphin.Model.Registry

/-!
# Market index, directory and terms

I3 is one active market per pair with a strictly increasing version; I4 is the
legal status transition.  The model keeps the index as an association list and
proves the two properties the arms rely on: a staged market is always `draft`,
and a delisted market accepts no further status.
-/

namespace Rholphin.Model.Market

open Rholphin

inductive MStatus where
  | draft
  | active
  | paused
  | delisted
  deriving DecidableEq, Repr

structure Terms where
  marketId : Nat
  slug : Nat
  base : Nat
  quote : Nat
  version : Nat

structure Slot where
  poolUri : Nat
  lockUri : Nat
  termsHash : Nat
  sealed : Bool

structure Market where
  status : MStatus
  version : Nat

structure Index where
  markets : List (Nat × Market)
  byPair : List (Nat × Nat)
  bySlug : List (Nat × Nat)

def lookupNat (entries : List (Nat × Nat)) (key : Nat) : Option Nat :=
  match entries with
  | [] => none
  | (k, v) :: rest => if k = key then some v else lookupNat rest key

def insertNat (entries : List (Nat × Nat)) (key value : Nat) : List (Nat × Nat) :=
  (key, value) :: entries

def lookupMarket (entries : List (Nat × Market)) (key : Nat) : Option Market :=
  match entries with
  | [] => none
  | (k, v) :: rest => if k = key then some v else lookupMarket rest key

def insertMarket (entries : List (Nat × Market)) (key : Nat) (v : Market) : List (Nat × Market) :=
  (key, v) :: entries

def lookupSlot (entries : List (Nat × Slot)) (key : Nat) : Option Slot :=
  match entries with
  | [] => none
  | (k, v) :: rest => if k = key then some v else lookupSlot rest key

def insertSlot (entries : List (Nat × Slot)) (key : Nat) (v : Slot) : List (Nat × Slot) :=
  (key, v) :: entries

/-- Terms are content-addressed; the hash is the store key. -/
def marketTerms_put (hash : Nat) : Option Nat := some hash

def marketTerms_get (store : List (Nat × Nat)) (hash : Nat) : Option Nat :=
  lookupNat store hash

structure Directory where
  slots : List (Nat × Slot)

def marketDirectory_bind (d : Directory) (marketId : Nat) (slot : Slot) : Option Directory :=
  match lookupSlot d.slots marketId with
  | some existing => if existing.sealed then none else some { d with slots := insertSlot d.slots marketId slot }
  | none => some { d with slots := insertSlot d.slots marketId slot }

def marketDirectory_seal (d : Directory) (marketId : Nat) : Option Directory :=
  match lookupSlot d.slots marketId with
  | none => none
  | some existing =>
      some { d with slots := insertSlot d.slots marketId { existing with sealed := true } }

def marketDirectory_byId (d : Directory) (marketId : Nat) : Option Slot :=
  lookupSlot d.slots marketId

def marketDirectory_slot (d : Directory) (marketId : Nat) : Option Slot :=
  lookupSlot d.slots marketId

/-! ## Status machine -/

def legal : MStatus → MStatus → Bool
  | .active, .paused => true
  | .active, .delisted => true
  | .paused, .active => true
  | .paused, .delisted => true
  | _, _ => false

theorem delisted_terminal (to : MStatus) : legal .delisted to = false := by
  cases to <;> rfl

def marketIndex_setStatus (m : Market) (to : MStatus) : Option Market :=
  if legal m.status to then some { m with status := to } else none

theorem delisted_accepts_nothing (m : Market) (to : MStatus) (h : m.status = .delisted) :
    marketIndex_setStatus m to = none := by
  cases m with
  | mk status version =>
      simp only at h
      subst h
      unfold marketIndex_setStatus
      rw [delisted_terminal to]
      rfl

/-- Staging refuses an active or paused pair and a non-increasing version. -/
def marketIndex_stage (i : Index) (marketId version : Nat) (prior : Option Market) : Option Index :=
  match lookupMarket i.markets marketId with
  | some _ => none
  | none =>
      match prior with
      | some p =>
          if p.status = .active ∨ p.status = .paused then none
          else if version ≤ p.version then none
          else some { i with markets := insertMarket i.markets marketId ⟨.draft, version⟩ }
      | none => some { i with markets := insertMarket i.markets marketId ⟨.draft, version⟩ }

theorem staged_is_draft {i i' : Index} {marketId version : Nat} {prior : Option Market}
    (h : marketIndex_stage i marketId version prior = some i') :
    (lookupMarket i'.markets marketId).map (fun m => m.status) = some .draft := by
  unfold marketIndex_stage at h
  split at h
  · contradiction
  · split at h
    · split at h
      · contradiction
      · split at h
        · contradiction
        · simp only [Option.some.injEq] at h
          subst h
          simp [lookupMarket]
    · simp only [Option.some.injEq] at h
      subst h
      simp [lookupMarket]

def marketIndex_activate (m : Market) : Option Market :=
  if m.status = .draft then some { m with status := .active } else none

def marketIndex_market (i : Index) (marketId : Nat) : Option Market :=
  lookupMarket i.markets marketId

def marketIndex_markets (i : Index) : List (Nat × Market) := i.markets

def marketIndex_marketFor (i : Index) (pair : Nat) : Option Market :=
  match lookupNat i.byPair pair with
  | none => none
  | some marketId => lookupMarket i.markets marketId

/-! ## Gate and views -/

def tradabilityGate_admit (status : MStatus) (fresh : Bool)
    (inputValue poolValue minTicket maxTradeBps : Nat) : Bool :=
  status == .active && fresh && inputValue ≥ minTicket
    && inputValue * Bps ≤ poolValue * maxTradeBps

def listingViews_marketFor (i : Index) (pair : Nat) : Option Market :=
  marketIndex_marketFor i pair
def listingViews_market (i : Index) (id : Nat) : Option Market := marketIndex_market i id
def listingViews_isActive (i : Index) (id : Nat) : Bool :=
  (marketIndex_market i id).any (fun m => m.status == .active)
def listingViews_terms (store : List (Nat × Nat)) (hash : Nat) : Option Nat :=
  marketTerms_get store hash
def listingViews_currency (store : List (Nat × Nat)) (code : Nat) : Option Nat :=
  lookupNat store code
def listingViews_currencies (store : List (Nat × Nat)) : List Nat := store.map (fun p => p.1)
def listingViews_markets (i : Index) : List (Nat × Market) := i.markets

/-- The factory stages a draft only after the sponsor, feed and pool checks. -/
def marketFactory_createMarket (checks : Bool) (i : Index) (marketId version : Nat) :
    Option Index :=
  if checks then marketIndex_stage i marketId version none else none

end Rholphin.Model.Market
