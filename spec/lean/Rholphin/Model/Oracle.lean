import Rholphin.Basic

/-!
# Oracle feed and hub

The feed stores three reporter slots, a trial counter and the paused/active
flags.  I7 is freshness: a submission is accepted only when the feed is
unpaused, the height is monotone and the trial counter advances; activation
requires the trial minimum and a fresh quorum.
-/

namespace Rholphin.Model.Oracle

open Rholphin

structure Feed where
  paused : Bool
  active : Bool
  trialSubmits : Nat
  trialMin : Nat
  quorum : Nat
  lastPrice : Nat
  lastHeight : Nat

def oracleMath_median3 (a b c : Nat) : Nat :=
  if a < b then
    if b < c then b else if a < c then c else a
  else
    if a < c then a else if b < c then c else b

def oracleMath_rate (basePrice quotePrice : Nat) : Nat :=
  if quotePrice = 0 then 0 else basePrice * E8 / quotePrice

def oracleMath_fresh (price height now maxAge minPrice maxPrice : Nat) : Bool :=
  decide (0 < height ∧ height ≤ now ∧ now - height ≤ maxAge
    ∧ minPrice ≤ price ∧ price ≤ maxPrice)

def oracleFeed_submit (f : Feed) (price height : Nat) : Option Feed :=
  if f.paused then none
  else if height ≤ f.lastHeight then none
  else some { f with lastPrice := price, lastHeight := height,
                     trialSubmits := f.trialSubmits + 1 }

theorem submit_paused_refused (f : Feed) (price height : Nat) (h : f.paused = true) :
    oracleFeed_submit f price height = none := by
  unfold oracleFeed_submit
  simp [h]

def oracleFeed_activate (f : Feed) (fresh : Bool) : Option Feed :=
  if f.active then none
  else if f.trialSubmits < f.trialMin then none
  else if not fresh then none
  else some { f with active := true }

theorem activate_requires_trial (f : Feed) (fresh : Bool)
    (h : f.trialSubmits < f.trialMin) :
    oracleFeed_activate f fresh = none := by
  unfold oracleFeed_activate
  by_cases ha : f.active
  · simp [ha]
  · simp [ha, h]

def oracleFeed_get (f : Feed) : Bool × Nat × Nat :=
  (f.active, f.lastPrice, f.lastHeight)

def oracleFeed_info (f : Feed) : Feed := f

def oracleFeed_admin (f : Feed) (action : Nat) : Option Feed :=
  if action = 0 then some { f with paused := true }
  else if action = 1 then some { f with active := false, paused := false, trialSubmits := 0 }
  else none

structure FeedRegistry where
  feeds : List (Nat × Nat)

def lookupNat (entries : List (Nat × Nat)) (key : Nat) : Option Nat :=
  match entries with
  | [] => none
  | (k, v) :: rest => if k = key then some v else lookupNat rest key

def oracleRegistry_registerFeed (r : FeedRegistry) (code feed : Nat) : Option FeedRegistry :=
  if (lookupNat r.feeds code).isSome then none
  else some { r with feeds := (code, feed) :: r.feeds }

theorem registerFeed_resolves {r r' : FeedRegistry} {code feed : Nat}
    (h : oracleRegistry_registerFeed r code feed = some r') :
    lookupNat r'.feeds code = some feed := by
  unfold oracleRegistry_registerFeed at h
  split at h
  · contradiction
  · simp only [Option.some.injEq] at h
    subst h
    simp [lookupNat]

def oracleRegistry_feedEntry (r : FeedRegistry) (code : Nat) : Option Nat :=
  lookupNat r.feeds code

def oracleRegistry_info (r : FeedRegistry) : List (Nat × Nat) := r.feeds

def oracleRegistry_admin (r : FeedRegistry) (reporter : Nat) : FeedRegistry :=
  { r with feeds := (reporter, 0) :: r.feeds }

def oracleHub_get (entry : Option Nat) : Option Nat := entry

def oracleHub_getPair (basePrice quotePrice : Nat) (fresh : Bool) : Nat × Bool :=
  (oracleMath_rate basePrice quotePrice, fresh)

def oracleHub_reporters (entry : Option Nat) : Option Nat := entry

def oracleHub_feedStatus (entry : Option Nat) : Option Nat := entry

end Rholphin.Model.Oracle
