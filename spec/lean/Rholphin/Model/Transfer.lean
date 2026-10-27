import Rholphin.Model.Types

/-!
# Transfer contract

One cell per transfer.  `claim` and `refund` both require status `open`, so
exactly one can win (I14); a terminal transfer keeps its cell and refuses with
`closed`.  The statement is proved as a two-step theorem: after a successful
claim there is no refund, and after a successful refund there is no claim.
-/

namespace Rholphin.Model.Transfer

open Rholphin

inductive Status where
  | open
  | claimed
  | refunded
  deriving DecidableEq, Repr

structure Transfer where
  status : Status
  memo : Nat
  opId : Nat
  stipend : Nat

def transferBook_send (memo opId stipend : Nat) : Transfer :=
  { status := Status.open, memo := memo, opId := opId, stipend := stipend }

def transferContract_claim (t : Transfer) (expired secretOk : Bool) : Option Transfer :=
  if t.status = Status.open ∧ expired = false ∧ secretOk = true then
    some { t with status := Status.claimed }
  else none

def transferContract_refund (t : Transfer) (expired senderOk : Bool) : Option Transfer :=
  if t.status = Status.open ∧ expired = true ∧ senderOk = true then
    some { t with status := Status.refunded }
  else none

def transferContract_info (t : Transfer) : Status × Nat × Nat × Nat :=
  (t.status, t.memo, t.opId, t.stipend)

/-- A successful claim is terminal for refunds. -/
theorem claim_then_refund_refused {t t' : Transfer} {expired secretOk : Bool}
    (h : transferContract_claim t expired secretOk = some t')
    (expired' senderOk : Bool) :
    transferContract_refund t' expired' senderOk = none := by
  unfold transferContract_claim at h
  split at h
  · rename_i hguard
    simp only [Option.some.injEq] at h
    subst h
    unfold transferContract_refund
    simp
  · contradiction

/-- A successful refund is terminal for claims. -/
theorem refund_then_claim_refused {t t' : Transfer} {expired senderOk : Bool}
    (h : transferContract_refund t expired senderOk = some t')
    (expired' secretOk : Bool) :
    transferContract_claim t' expired' secretOk = none := by
  unfold transferContract_refund at h
  split at h
  · rename_i hguard
    simp only [Option.some.injEq] at h
    subst h
    unfold transferContract_claim
    simp
  · contradiction

end Rholphin.Model.Transfer
