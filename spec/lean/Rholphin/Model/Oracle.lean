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

/-! ## I8: reporter set -/

/-- Three distinct reporter keys, with the sponsor in at most one slot. -/
def reportersOk (keys : List Nat) (sponsor : Nat) : Bool :=
  decide (keys.Nodup ∧ keys.length = 3 ∧ (keys.filter (fun k => k = sponsor)).length ≤ 1)

theorem reportersOk_nodup {keys : List Nat} {sponsor : Nat}
    (h : reportersOk keys sponsor = true) : keys.Nodup := by
  unfold reportersOk at h
  exact (of_decide_eq_true h).1

theorem reportersOk_length {keys : List Nat} {sponsor : Nat}
    (h : reportersOk keys sponsor = true) : keys.length = 3 := by
  unfold reportersOk at h
  exact (of_decide_eq_true h).2.1

theorem reportersOk_sponsor {keys : List Nat} {sponsor : Nat}
    (h : reportersOk keys sponsor = true) :
    (keys.filter (fun k => k = sponsor)).length ≤ 1 := by
  unfold reportersOk at h
  exact (of_decide_eq_true h).2.2

/-! ## I9: pair freshness -/

structure PairQuote where
  baseRate : Nat
  quoteRate : Nat
  baseHeight : Nat
  quoteHeight : Nat
  now : Nat
  maxAge : Nat

def PairQuote.fresh (q : PairQuote) : Prop :=
  q.baseHeight ≤ q.now ∧ q.quoteHeight ≤ q.now ∧
    q.now - q.baseHeight ≤ q.maxAge ∧ q.now - q.quoteHeight ≤ q.maxAge

def PairQuote.freshOk (q : PairQuote) : Bool :=
  decide (q.baseHeight ≤ q.now ∧ q.quoteHeight ≤ q.now ∧
    q.now - q.baseHeight ≤ q.maxAge ∧ q.now - q.quoteHeight ≤ q.maxAge)

def pairRate (q : PairQuote) : Option Nat :=
  if q.freshOk then some (oracleMath_rate q.baseRate q.quoteRate) else none

theorem stale_pair_refused {q : PairQuote} (h : ¬ q.fresh) : pairRate q = none := by
  unfold pairRate
  have hok : q.freshOk = false := by
    unfold PairQuote.freshOk
    exact decide_eq_false (by simpa [PairQuote.fresh] using h)
  simp [hok]

theorem pair_rate_ages {q : PairQuote} {r : Nat} (h : pairRate q = some r) :
    q.now - q.baseHeight ≤ q.maxAge ∧ q.now - q.quoteHeight ≤ q.maxAge := by
  unfold pairRate at h
  split at h
  · rename_i hok
    have hdec : decide (q.baseHeight ≤ q.now ∧ q.quoteHeight ≤ q.now ∧
        q.now - q.baseHeight ≤ q.maxAge ∧ q.now - q.quoteHeight ≤ q.maxAge) = true := by
      simpa [PairQuote.freshOk] using hok
    have hf := of_decide_eq_true hdec
    exact ⟨hf.2.2.1, hf.2.2.2⟩
  · contradiction

end Rholphin.Model.Oracle
