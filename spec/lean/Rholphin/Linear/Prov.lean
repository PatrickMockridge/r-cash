import Rholphin.Basic

/-!
# Capability provenance

A name's provenance is the authority it carries.  `fresh` names are created by
`new` in the component, `installer` names are pinned by the bootstrap/Root,
`issuer` names are returned by an authority in a documented arm, and `caller`
names are supplied by an arbitrary caller.  A caller name is a sink facet, a
payment or a reply channel: it is never an authority, it is never stored as
one, and it may not be captured by a published bundle.

These are the model obligations behind C1/C1a/C3 and I20.  The deploy source is
related to the model by `tools/check_capabilities.py` and the red-team suite;
this module proves the rules themselves, not the source's adherence to them.
-/

namespace Rholphin.Linear

inductive Prov
  | fresh
  | installer
  | issuer
  | caller
  deriving DecidableEq, Repr

namespace Prov

/-- Authority use: fresh, installer and issuer names may be used as authority. -/
def isAuthority : Prov → Bool
  | fresh => true
  | installer => true
  | issuer => true
  | caller => false

/-- Bundleability: a caller name is not authority, and a bundle may not close
over a registry-resolved (installer) capability (C3). -/
def bundleable : Prov → Bool
  | fresh => true
  | installer => false
  | issuer => true
  | caller => false

end Prov

structure Name where
  id : Nat
  prov : Prov

/-- Store a name in a state position.  Only an authority may be stored. -/
def store (state : List Name) (n : Name) : Option (List Name) :=
  if n.prov.isAuthority then some (n :: state) else none

/-- A caller-supplied name is never stored as authority. -/
theorem caller_never_stored (state : List Name) (n : Name)
    (h : n.prov = Prov.caller) : store state n = none := by
  simp [store, h, Prov.isAuthority]

/-- Every authority use has a non-caller provenance. -/
theorem authority_use_requires_provenance (n : Name)
    (h : n.prov.isAuthority = true) : n.prov ≠ Prov.caller := by
  intro hc
  rw [hc] at h
  cases h

/-- C3: a bundle's names are all bundleable. -/
def bundleOK (names : List Name) : Prop :=
  ∀ n ∈ names, n.prov.bundleable = true

/-- A bundle that closes over an installer (registry-resolved) name is not a
valid bundle. -/
theorem bundle_no_registry_cap (names : List Name) (n : Name)
    (hmem : n ∈ names) (h : n.prov = Prov.installer) : ¬ bundleOK names := by
  intro hok
  have hbundle := hok n hmem
  simp [h, Prov.bundleable] at hbundle

end Rholphin.Linear
