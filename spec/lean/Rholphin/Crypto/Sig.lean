import Rholphin.Basic

/-!
# Signatures

`SigScheme` is the abstract verifier; unforgeability is an explicit hypothesis.
The model's old `verifier_sigOk ok := ok` is replaced by
`SigScheme.verify`, so a theorem about authority is conditional on the scheme
being unforgeable rather than on the identity function.
-/

namespace Rholphin

/-- A public key identity. -/
structure Key where
  id : Nat
  deriving DecidableEq, Repr

/-- A signature over a message. -/
structure Sig where
  signer : Nat
  message : Nat
  deriving DecidableEq, Repr

/-- A signature verifier. -/
structure SigScheme where
  verify : Key → Nat → Sig → Bool

/-- Unforgeability: a verifying signature names the key that made it. -/
def Unforgeable (S : SigScheme) : Prop :=
  ∀ k m sig, S.verify k m sig = true → sig.signer = k.id

/-- A verified signature names the signer. -/
theorem verify_true_implies_signer {S : SigScheme} (hunf : Unforgeable S)
    {k : Key} {m : Nat} {sig : Sig} (h : S.verify k m sig = true) :
    sig.signer = k.id :=
  hunf k m sig h

/-- A signature over a different message is not a signature over this one. -/
def SignedOver (S : SigScheme) (k : Key) (m : Nat) (sig : Sig) : Prop :=
  S.verify k m sig = true

/-- The deployer/sponsor gate: the caller's key is the one named by the signature. -/
def Authorized (S : SigScheme) (k : Key) (m : Nat) (sig : Sig) : Prop :=
  SignedOver S k m sig ∧ sig.signer = k.id

theorem authorized_imp_signer {S : SigScheme} (hunf : Unforgeable S)
    {k : Key} {m : Nat} {sig : Sig} (h : Authorized S k m sig) :
    sig.signer = k.id :=
  verify_true_implies_signer hunf h.1

end Rholphin
