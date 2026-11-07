import Rholphin.Basic

/-!
# Canonical encoding

The deployed encoding is length-prefixed before the `|` join, so a value that
contains `|` cannot collide with another tuple.  The model names that property
`Canonical` and leaves the encoder abstract.
-/

namespace Rholphin

/-- An encoder from a schema and ordered values to bytes, modelled as naturals. -/
def Encoding := Nat → List Nat → List Nat

/-- Distinct schema/values pairs encode distinctly. -/
def Canonical (enc : Encoding) : Prop :=
  ∀ s v s' v', enc s v = enc s' v' → s = s' ∧ v = v'

/-- Under canonicity, equal encodings are exactly equal inputs. -/
theorem codec_no_pipe_collision {enc : Encoding} (hc : Canonical enc) {s s' : Nat}
    {vs vs' : List Nat} :
    enc s vs = enc s' vs' ↔ s = s' ∧ vs = vs' := by
  constructor
  · exact hc s vs s' vs'
  · intro h
    rcases h with ⟨rfl, rfl⟩
    rfl

/-- Canonical encoding preserves injectivity. -/
theorem codec_injective {enc : Encoding} (hc : Canonical enc) :
    ∀ p q : Nat × List Nat, enc p.1 p.2 = enc q.1 q.2 → p = q := by
  intro p q h
  have hp := hc p.1 p.2 q.1 q.2 h
  exact Prod.ext hp.1 hp.2

end Rholphin
