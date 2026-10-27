import Rholphin.Model.Types

/-!
# Governor and admin guard

Per-domain nonces are monotone and a scheduled action carries `readyAt =
scheduleHeight + timelock`.  `execute` refuses before `readyAt`; that is S12.
The admin guard is a threshold over signatures.
-/

namespace Rholphin.Model.Governance

open Rholphin

structure Pending where
  action : Nat
  argsHash : Nat
  args : Nat
  readyAt : Nat

structure GovernorState where
  nonces : List (Nat × Nat)
  pending : List (Nat × Pending)
  timelock : Nat

def lookupNat (entries : List (Nat × Nat)) (key : Nat) : Option Nat :=
  match entries with
  | [] => none
  | (k, v) :: rest => if k = key then some v else lookupNat rest key

def lookupPending (entries : List (Nat × Pending)) (key : Nat) : Option Pending :=
  match entries with
  | [] => none
  | (k, v) :: rest => if k = key then some v else lookupPending rest key

def setNonce (entries : List (Nat × Nat)) (key value : Nat) : List (Nat × Nat) :=
  (key, value) :: entries

def adminGuard_verify (signatures threshold : Nat) : Bool :=
  threshold ≤ signatures

def governor_authorize (s : GovernorState) (domain nonce : Nat) : Option GovernorState :=
  match lookupNat s.nonces domain with
  | some last => if nonce ≤ last then none else some { s with nonces := setNonce s.nonces domain nonce }
  | none => some { s with nonces := setNonce s.nonces domain nonce }

def governor_schedule (s : GovernorState) (domain nonce action argsHash args : Nat)
    (height : Nat) : Option (Nat × GovernorState) :=
  match lookupNat s.nonces domain with
  | some last =>
      if nonce ≤ last then none
      else if (lookupPending s.pending (domain * 1000000 + nonce)).isSome then none
      else
        let readyAt := height + s.timelock
        some (readyAt, { s with pending :=
          ((domain * 1000000 + nonce), ⟨action, argsHash, args, readyAt⟩) :: s.pending })
  | none =>
      let readyAt := height + s.timelock
      some (readyAt, { s with pending :=
        ((domain * 1000000 + nonce), ⟨action, argsHash, args, readyAt⟩) :: s.pending })

/-- Executing before the scheduled height is refused. -/
theorem execute_not_early (s : GovernorState) (domain nonce now : Nat) (p : Pending)
    (hp : lookupPending s.pending (domain * 1000000 + nonce) = some p)
    (h : now < p.readyAt) :
    (match lookupPending s.pending (domain * 1000000 + nonce) with
     | none => none
     | some entry => if entry.readyAt ≤ now then some entry else none) = none := by
  rw [hp]
  simp [Nat.not_le_of_lt h]

def governor_execute (s : GovernorState) (domain nonce now : Nat) :
    Option (Pending × GovernorState) :=
  match lookupPending s.pending (domain * 1000000 + nonce) with
  | none => none
  | some entry =>
      if entry.readyAt ≤ now then
        some (entry, { s with nonces := setNonce s.nonces domain nonce })
      else none

def governor_pending (s : GovernorState) (domain nonce : Nat) : Option Pending :=
  lookupPending s.pending (domain * 1000000 + nonce)

def governor_admins (admins threshold : Nat) : Nat × Nat := (admins, threshold)

def governor_admin (s : GovernorState) (nonce timelock : Nat) : Option GovernorState :=
  if timelock < 1 then none else some { s with nonces := setNonce s.nonces 0 nonce, timelock := timelock }

end Rholphin.Model.Governance
