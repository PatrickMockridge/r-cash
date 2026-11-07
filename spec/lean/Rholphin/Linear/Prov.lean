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

/-!
## Facet-kind attenuation

A provisioned facet is narrower than the raw issuer auth: it may use only the
auths of its own operation.  `FacetKind.allows` is the whitelist, and
`facetStore` refuses a name whose kind or auth is outside the facet's scope.
This is the model obligation behind the multi-term facet ABI
(`docs/spec/MULTI-TERM.md` §3) and OCAP-06.
-/

/-- The five facets named by the multi-term ABI. -/
inductive FacetKind where
  | mint
  | burn
  | settle
  | custody
  | bufferOperator
  deriving DecidableEq, Repr

namespace FacetKind

/-- The authority scope of each facet.  A mint facet is not a burn facet. -/
def scope : FacetKind → List String
  | mint => ["mintAuth"]
  | burn => ["burnAuth"]
  | settle => ["settlementAuth"]
  | custody => ["custodyAuth"]
  | bufferOperator => ["bufferDepositAuth", "bufferPayAuth", "bufferCoverAuth"]

/-- Executable whitelist used by the store rule.  Written by cases so a closed
membership fact reduces definitionally. -/
def allows : FacetKind → String → Bool
  | mint, "mintAuth" => true
  | burn, "burnAuth" => true
  | settle, "settlementAuth" => true
  | custody, "custodyAuth" => true
  | bufferOperator, "bufferDepositAuth" => true
  | bufferOperator, "bufferPayAuth" => true
  | bufferOperator, "bufferCoverAuth" => true
  | _, _ => false

end FacetKind

/-- A name a facet holds, tagged with the facet kind and the operation auth it
is intended for. -/
structure ScopedName where
  name : Name
  kind : FacetKind
  auth : String

/-- A facet of kind `k` may store a scoped name only when the name belongs to
the same kind and the auth is inside that kind's scope. -/
def facetStore (k : FacetKind) (state : List ScopedName) (n : ScopedName) :
    Option (List ScopedName) :=
  if n.kind = k ∧ k.allows n.auth then some (n :: state) else none

/-- Any name a facet stores is inside the facet's own authority scope. -/
theorem facet_store_scope {k : FacetKind} {state : List ScopedName} {n : ScopedName}
    {s : List ScopedName} (h : facetStore k state n = some s) : k.allows n.auth = true := by
  unfold facetStore at h
  split at h
  · rename_i hc
    exact hc.2
  · contradiction

/-- Attenuation: a facet cannot store a name of a different kind. -/
theorem facet_store_rejects_foreign_kind (k : FacetKind) (state : List ScopedName)
    (n : ScopedName) (h : n.kind ≠ k) : facetStore k state n = none := by
  simp [facetStore, h]

/-- Attenuation: a facet cannot store a name whose auth is outside its scope. -/
theorem facet_store_rejects_foreign_auth (k : FacetKind) (state : List ScopedName)
    (n : ScopedName) (h : k.allows n.auth = false) : facetStore k state n = none := by
  simp [facetStore, h]

/-- The mint facet cannot acquire the burn authority. -/
theorem mint_facet_cannot_store_burn_auth (state : List ScopedName) (n : ScopedName)
    (hk : n.kind = FacetKind.mint) (hauth : n.auth = "burnAuth") :
    facetStore FacetKind.mint state n = none := by
  simp [facetStore, hk, hauth, FacetKind.allows]

/-- The burn facet cannot acquire the mint authority. -/
theorem burn_facet_cannot_store_mint_auth (state : List ScopedName) (n : ScopedName)
    (hk : n.kind = FacetKind.burn) (hauth : n.auth = "mintAuth") :
    facetStore FacetKind.burn state n = none := by
  simp [facetStore, hk, hauth, FacetKind.allows]

/-!
## The revised facet ABI

The facet signatures mirror the privileged arms they wrap.  In particular,
`burn`, `settle`, `custody.deposit` and `buffer.deposit` carry a payment; a
facet never invents a different shape from its arm.  These definitions make the
ABI checkable and the payment-carrying arms explicit.
-/

/-- One call to a provisioned facet. -/
inductive FacetArm where
  | mint (amount : Nat)
  | burn (payment : Bool) (maxAmount : Nat)
  | settle (payment : Bool) (principal interest : Nat)
  | custodyDeposit (payment : Bool)
  | custodyWithdraw (amount : Nat)
  | bufferDeposit (payment : Bool)
  | bufferPaySavings (amount : Nat)
  | bufferCover (amount : Nat)
  deriving DecidableEq, Repr

namespace FacetArm

/-- The facet kind that owns the arm. -/
def kind : FacetArm → FacetKind
  | mint _ => .mint
  | burn _ _ => .burn
  | settle _ _ _ => .settle
  | custodyDeposit _ => .custody
  | custodyWithdraw _ => .custody
  | bufferDeposit _ => .bufferOperator
  | bufferPaySavings _ => .bufferOperator
  | bufferCover _ => .bufferOperator

/-- The payment-carrying arms of the revised ABI. -/
def carriesPayment : FacetArm → Bool
  | burn _ _ => true
  | settle _ _ _ => true
  | custodyDeposit _ => true
  | bufferDeposit _ => true
  | _ => false

/-- A facet of kind `k` may be called only with its own arm. -/
def callAllowed (k : FacetKind) (a : FacetArm) : Bool := k == a.kind

end FacetArm

/-- A burn facet call carries a payment. -/
theorem burn_facet_call_carries_payment (a : FacetArm)
    (h : FacetArm.callAllowed .burn a = true) : a.carriesPayment = true := by
  cases a <;> simp_all [FacetArm.callAllowed, FacetArm.carriesPayment, FacetArm.kind]

/-- A settle facet call carries a payment. -/
theorem settle_facet_call_carries_payment (a : FacetArm)
    (h : FacetArm.callAllowed .settle a = true) : a.carriesPayment = true := by
  cases a <;> simp_all [FacetArm.callAllowed, FacetArm.carriesPayment, FacetArm.kind]

/-- A custody deposit carries a payment; a custody withdraw does not. -/
theorem custody_deposit_carries_payment (a : FacetArm)
    (h : FacetArm.callAllowed .custody a = true)
    (hdep : a = .custodyDeposit true ∨ a = .custodyDeposit false) :
    a.carriesPayment = true := by
  rcases hdep with rfl | rfl <;> simp [FacetArm.carriesPayment]

/-- A buffer deposit carries a payment. -/
theorem buffer_deposit_carries_payment (a : FacetArm)
    (h : FacetArm.callAllowed .bufferOperator a = true)
    (hdep : a = .bufferDeposit true ∨ a = .bufferDeposit false) :
    a.carriesPayment = true := by
  rcases hdep with rfl | rfl <;> simp [FacetArm.carriesPayment]

/-- The mint facet call never carries a payment. -/
theorem mint_facet_call_carries_no_payment (a : FacetArm)
    (h : FacetArm.callAllowed .mint a = true) : a.carriesPayment = false := by
  cases a <;> simp_all [FacetArm.callAllowed, FacetArm.carriesPayment, FacetArm.kind]

/-- A facet call is allowed only when its arm belongs to the facet kind. -/
theorem allowed_arm_has_kind (k : FacetKind) (a : FacetArm)
    (h : FacetArm.callAllowed k a = true) : a.kind = k := by
  cases a <;> simp_all [FacetArm.callAllowed]

end Rholphin.Linear
