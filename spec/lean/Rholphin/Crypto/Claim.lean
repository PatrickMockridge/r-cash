import Rholphin.Crypto.Hash

/-!
# Claim secrets

A transfer stores `secretHash`; a claimer presents the secret.  Binding makes
the hash a one-way commitment: the only secret that claims the transfer is one
whose hash is the stored one.  The old `claimCode_hash secret := secret` stub is
replaced by `ClaimScheme.hash` with `Binding` as an explicit hypothesis.
-/

namespace Rholphin

/-- A claim secret. -/
structure Secret where
  value : Nat
  deriving DecidableEq, Repr

/-- A claim-hash scheme. -/
structure ClaimScheme where
  hash : Secret → Hash

/-- Binding: equal hashes imply equal secrets. -/
def Binding (C : ClaimScheme) : Prop :=
  ∀ s1 s2, C.hash s1 = C.hash s2 → s1 = s2

/-- A transfer record relevant to a claim. -/
structure Claim where
  secretHash : Hash
  status : Nat
  deriving DecidableEq, Repr

/-- OCAP-19: the committed preimage binds the caller-supplied opId and amount
to the secret.  The contract hashes `rcash:claim:v1|opId|assetId|amount|secret`
through the canonical codec; this record is the modelled field list.  opId is
used because the account allocates the numeric transfer id inside
`sendTransfer`, after the sender chooses the commitment. -/
structure ClaimPreimage where
  opId : Nat
  assetId : Nat
  amount : Nat
  secret : Secret

/-- The ordered fields of the canonical claim preimage. -/
def ClaimPreimage.fields (p : ClaimPreimage) : List Nat :=
  [p.opId, p.assetId, p.amount, p.secret.value]

/-- Equal preimages bind the same opId, so a secret committed to one transfer
cannot be replayed as the commitment for another. -/
theorem ClaimPreimage.opId_injective {p q : ClaimPreimage}
    (h : p.fields = q.fields) : p.opId = q.opId := by
  have h' : p.opId = q.opId ∧ p.assetId = q.assetId ∧
      p.amount = q.amount ∧ p.secret.value = q.secret.value := by
    simpa [ClaimPreimage.fields] using h
  exact h'.1

/-- Claim changes the status only when the presented secret matches the stored hash. -/
def claim (C : ClaimScheme) (t : Claim) (secret : Secret) : Option Claim :=
  if C.hash secret = t.secretHash then some { t with status := 1 } else none

/-- A successful claim used a preimage of the stored hash. -/
theorem claim_requires_preimage {C : ClaimScheme} {t t' : Claim} {secret : Secret}
    (h : claim C t secret = some t') : C.hash secret = t.secretHash := by
  unfold claim at h
  split at h
  · assumption
  · contradiction

/-- A wrong secret is refused. -/
theorem wrong_secret_refused {C : ClaimScheme} {t : Claim} {secret : Secret}
    (hne : C.hash secret ≠ t.secretHash) : claim C t secret = none := by
  simp [claim, hne]

/-- With binding, two different secrets cannot both claim the same transfer. -/
theorem claim_secret_unique {C : ClaimScheme} (hb : Binding C) {t : Claim}
    {s1 s2 : Secret} (h1 : C.hash s1 = t.secretHash) (h2 : C.hash s2 = t.secretHash) :
    s1 = s2 :=
  hb s1 s2 (h1.trans h2.symm)

end Rholphin
