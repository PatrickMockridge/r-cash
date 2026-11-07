import Rholphin.Basic

/-!
# Content addressing

The deployed terms use blake2b256 over a length-prefixed encoding.  The model
does not implement the hash; it names the interface and makes collision
resistance an explicit hypothesis.  `terms_put_integrity` is then a theorem
about the store, not about the hash function.

This replaces the `marketTerms_put hash := some hash` stub: a store accepts a
hash only if it equals the hash computed from the terms.
-/

namespace Rholphin

/-- A digest.  The model treats it as an opaque natural. -/
structure Hash where
  digest : Nat
  deriving DecidableEq, Repr

/-- The schema tag and the ordered values of a canonical group. -/
abbrev Schema := Nat
abbrev Values := List Nat

/-- A content-addressing function. -/
def Hasher := Schema → Values → Hash

/-- Collision resistance, as an explicit hypothesis. -/
def CollisionResistant (H : Hasher) : Prop :=
  ∀ s v s' v', H s v = H s' v' → s = s' ∧ v = v'

/-- A content-addressed store keyed by a hash. -/
def TermsPut (H : Hasher) (hash : Hash) (schema : Schema) (values : Values) : Option Hash :=
  if H schema values = hash then some hash else none

/-- A stored hash is the hash of the stored terms. -/
theorem terms_put_integrity {H : Hasher} {hash hash' : Hash} {schema : Schema}
    {values : Values} (h : TermsPut H hash schema values = some hash') :
    hash' = H schema values := by
  unfold TermsPut at h
  split at h
  · rename_i hcond
    injection h with heq
    subst heq
    exact hcond.symm
  · contradiction

/-- A mismatched hash is refused, so the store cannot be made to hold a false key. -/
theorem terms_put_rejects_mismatch {H : Hasher} {hash : Hash} {schema : Schema}
    {values : Values} (hne : H schema values ≠ hash) :
    TermsPut H hash schema values = none := by
  simp [TermsPut, hne]

/-- Collision resistance makes distinct terms have distinct hashes. -/
theorem hash_distinct {H : Hasher} (hCR : CollisionResistant H) {s s' : Nat}
    {v v' : Values} (hne : s ≠ s' ∨ v ≠ v') : H s v ≠ H s' v' := by
  intro heq
  exact hne.elim (fun hs => hs (hCR s v s' v' heq).1)
    (fun hv => hv (hCR s v s' v' heq).2)

end Rholphin
