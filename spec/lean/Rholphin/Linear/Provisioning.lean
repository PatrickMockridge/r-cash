import Rholphin.Linear.Prov

/-!
# Provisioning (P5 reserve/confirm, P7 intra-deploy grant)

The multi-term architecture delivers an issuer facet through a sponsor-signed,
one-shot `FacetShop.provision` call (`docs/spec/MULTI-TERM.md` §4).  The shop:

1. verifies the sponsor key it bound at creation and the signed canonical
   payload (issuer, consumer, kinds, nonce, deadline);
2. consumes the nonce;
3. resolves the pinned consumer URI from the payload and calls
   `acceptFacet` in the same deploy;
4. `fail()`s on any refusal, so the nonce and every slot roll back.

The consumer verifies the facet with `isFacet` and writes it once to a private
bare-name slot (L7).  No facet name is returned to the caller.

This module proves the four protocol obligations:

* `nonce_cannot_provision_twice` — a consumed nonce cannot provision twice;
* `forged_facet_refused` — a facet the shop did not issue is refused;
* `provision_returns_no_cap` — the caller-visible reply carries no capability;
* `rotation_preserves_facet` / `rotation_refuses_old` — rotation keeps the
  facet live and refuses the old auth.

The model is abstract: signatures are represented by an equality against the
shop's bound sponsor, and names are `Nat` identifiers.  `check_capabilities.py`
and the red-team suite relate it to the deploy source.
-/

namespace Rholphin.Linear

/-- A capability identifier.  Fresh names are opaque; `Nat` is enough to reason
about identity and distinctness. -/
abbrev CapName := Nat

/-- Each facet-owning deploy term publishes its own shop.  T1 owns the issuer
facets; T3 owns the buffer facet; a single central shop cannot issue a facet
that lives in another term's closure. -/
inductive ShopTerm where
  | issuer
  | buffer
  deriving DecidableEq, Repr

/-- The shop pinned for a facet kind.  A consumer maps each kind to exactly one
shop and verifies the delivered facet with that shop's `isFacet`. -/
def pinnedShop : FacetKind → ShopTerm
  | .mint => .issuer
  | .burn => .issuer
  | .settle => .issuer
  | .custody => .issuer
  | .bufferOperator => .buffer

/-- The shop's persistent state.  It binds the sponsor, its term and its own
issuer URI at creation, records every facet it has issued, and records
consumed nonces. -/
structure Shop where
  term : ShopTerm
  sponsor : String
  issuerUri : String
  issued : List (FacetKind × CapName)
  consumed : List Nat
  deriving Repr

/-- The canonical provisioning payload (`rcash:provision:v1`).  The shop
resolves the consumer URI from this value, never from a caller argument. -/
structure ProvisionRequest where
  issuerUri : String
  consumerUri : String
  consumerTag : String
  kinds : List FacetKind
  nonce : Nat
  deadline : Nat
  sponsorHex : String
  deriving Repr

/-- The facets granted to the consumer.  This value is delivered in the same
deploy; it is never the shop's reply to the caller. -/
structure Delivery where
  consumerUri : String
  facets : List (FacetKind × CapName)

/-- The caller-visible reply.  It names no capability. -/
inductive Reply where
  | provisioned (consumerUri : String) (kinds : List FacetKind)
  | refused (reason : String)
  deriving DecidableEq, Repr

/-- The only names a reply can expose.  `provisioned` and `refused` expose
none; the function exists so "no capability returned" is a theorem about the
reply type, not a convention. -/
def Reply.capNames : Reply → List CapName
  | .provisioned _ _ => []
  | .refused _ => []

/-- Does the shop hold an issued facet of this kind? -/
def Shop.hasKind (shop : Shop) (k : FacetKind) : Bool :=
  shop.issued.any (fun (kind, _) => kind == k)

/-- Is this shop the one pinned for the kind?  T1 may not issue a T3 facet. -/
def Shop.canIssue (shop : Shop) (k : FacetKind) : Bool :=
  shop.term == pinnedShop k

/-- The shop's own name for a kind.  The fleet is created by the shop, so the
consumer never supplies this value. -/
def Shop.nameFor (shop : Shop) (k : FacetKind) : CapName :=
  match shop.issued.find? (fun (kind, _) => kind == k) with
  | some (_, name) => name
  | none => 0

/-- The provisioning guard.  The sponsor and issuer are bound at creation; the
deadline is checked; the nonce is unconsumed; every requested kind is issued by
this shop, and this shop is the one pinned for the kind. -/
def provisionGuard (shop : Shop) (now : Nat) (req : ProvisionRequest) : Prop :=
  shop.sponsor = req.sponsorHex ∧
  shop.issuerUri = req.issuerUri ∧
  now ≤ req.deadline ∧
  req.nonce ∉ shop.consumed ∧
  req.kinds.all (fun k => shop.hasKind k && shop.canIssue k) = true

/-- The guard is decidable: every component is decidable. -/
instance provisionGuardDecidable (shop : Shop) (now : Nat) (req : ProvisionRequest) :
    Decidable (provisionGuard shop now req) := by
  unfold provisionGuard
  infer_instance

/-- Reserve the nonce by writing it into the shop state. -/
def Shop.consume (shop : Shop) (n : Nat) : Shop :=
  { shop with consumed := n :: shop.consumed }

/-- The facet bundle the shop hands to the pinned consumer. -/
def deliveryFor (shop : Shop) (req : ProvisionRequest) : Delivery :=
  { consumerUri := req.consumerUri,
    facets := req.kinds.map (fun k => (k, shop.nameFor k)) }

/-- P7: the intra-deploy grant.  `acceptOk` is the consumer's `acceptFacet`
result.  A false result models `fail()`: the whole deploy, including the
nonce reservation, rolls back.  The caller sees only an `Ack`-shaped reply and
never the delivered facets. -/
def provision (shop : Shop) (now : Nat) (req : ProvisionRequest) (acceptOk : Bool) :
    Shop × Reply :=
  if _ : provisionGuard shop now req then
    if acceptOk then
      (shop.consume req.nonce, .provisioned req.consumerUri req.kinds)
    else
      (shop, .refused "accept refused")
  else
    (shop, .refused "bad provision request")

/-- A successful provisioning reply implies the guard held. -/
theorem provision_guard_of_provisioned {shop : Shop} {now : Nat} {req : ProvisionRequest}
    (h : (provision shop now req true).2 = .provisioned req.consumerUri req.kinds) :
    provisionGuard shop now req := by
  by_cases hg : provisionGuard shop now req
  · exact hg
  · simp [provision, hg] at h

/-- A successful provisioning consumes its nonce. -/
theorem provision_consumes_nonce {shop : Shop} {now : Nat} {req : ProvisionRequest}
    (h : (provision shop now req true).2 = .provisioned req.consumerUri req.kinds) :
    req.nonce ∈ (provision shop now req true).1.consumed := by
  have hg := provision_guard_of_provisioned h
  simp [provision, hg, Shop.consume]

/-- Per-term shops: a kind can only be provisioned by the shop pinned for it.
This is the model obligation that a consumer verifies a facet against the shop
pinned for that kind. -/
theorem provision_requires_pinned_shop (shop : Shop) (now : Nat)
    (req : ProvisionRequest) (k : FacetKind) (hk : k ∈ req.kinds)
    (h : (provision shop now req true).2 = .provisioned req.consumerUri req.kinds) :
    shop.term = pinnedShop k := by
  have hg := provision_guard_of_provisioned h
  have hall : (req.kinds.all (fun k => shop.hasKind k && shop.canIssue k)) = true :=
    hg.2.2.2.2
  have hkall : (shop.hasKind k && shop.canIssue k) = true :=
    (List.all_eq_true.mp hall) k hk
  have hcan : shop.canIssue k = true := by
    cases hc : shop.canIssue k with
    | true => rfl
    | false => simp [hc] at hkall
  simpa [Shop.canIssue] using hcan

/-- T1's issuer shop cannot issue the T3 buffer facet. -/
theorem issuer_shop_cannot_issue_buffer (shop : Shop) (h : shop.term = .issuer) :
    shop.canIssue .bufferOperator = false := by
  simp [Shop.canIssue, pinnedShop, h]

/-- T3's buffer shop cannot issue an issuer facet. -/
theorem buffer_shop_cannot_issue_mint (shop : Shop) (h : shop.term = .buffer) :
    shop.canIssue .mint = false := by
  simp [Shop.canIssue, pinnedShop, h]

/-- (a) Reserve/confirm: after a successful provisioning the same nonce cannot
provision a second time.  The second call sees the nonce in `consumed` and is
refused before any state change. -/
theorem nonce_cannot_provision_twice (shop : Shop) (now1 now2 : Nat)
    (req1 req2 : ProvisionRequest) (hnonce : req1.nonce = req2.nonce)
    (h1 : (provision shop now1 req1 true).2 = .provisioned req1.consumerUri req1.kinds) :
    (provision (provision shop now1 req1 true).1 now2 req2 true).2 ≠
      .provisioned req2.consumerUri req2.kinds := by
  intro h2
  have hcons := provision_consumes_nonce h1
  have hg2 := provision_guard_of_provisioned h2
  have hfresh : req2.nonce ∉ (provision shop now1 req1 true).1.consumed :=
    hg2.2.2.2.1
  exact hfresh (hnonce ▸ hcons)

/-- P7 rollback: a refusal from the consumer leaves the shop exactly as it was,
so the nonce is not consumed and no slot was written. -/
theorem provision_refusal_rolls_back (shop : Shop) (now : Nat) (req : ProvisionRequest) :
    (provision shop now req false).1 = shop := by
  by_cases hg : provisionGuard shop now req <;> simp [provision, hg]

/-- (c) No capability is returned: the caller-visible reply type exposes no
name, in either the success or the refusal case. -/
theorem provision_returns_no_cap (shop : Shop) (now : Nat) (req : ProvisionRequest)
    (acceptOk : Bool) : (provision shop now req acceptOk).2.capNames = [] := by
  by_cases hg : provisionGuard shop now req <;>
    by_cases ha : acceptOk <;>
    simp [provision, hg, ha, Reply.capNames]

/-- The facets requested are routed to the pinned consumer, not to the caller.
This is the P7 delivery half of the no-capability theorem. -/
theorem provision_routes_facets_to_consumer (shop : Shop) (req : ProvisionRequest)
    {k : FacetKind} (hk : k ∈ req.kinds) :
    (∃ name, (k, name) ∈ (deliveryFor shop req).facets) ∧
      (deliveryFor shop req).consumerUri = req.consumerUri := by
  constructor
  · exact ⟨shop.nameFor k, List.mem_map_of_mem (fun k => (k, shop.nameFor k)) hk⟩
  · rfl

/-- Does the shop consider `name` an issued facet of kind `k`?  This is the
`FacetShop.isFacet` predicate the consumer calls. -/
def Shop.isIssued (shop : Shop) (k : FacetKind) (name : CapName) : Bool :=
  shop.issued.any (fun (kind, n) => kind == k && n == name)

/-- The consumer's write-once slot.  `none` is an empty slot; `some current`
means a facet is already installed and a second write is refused. -/
def acceptFacet (shop : Shop) (k : FacetKind) (facet : CapName)
    (slot : Option CapName) : Option (Option CapName) :=
  if slot.isSome then none
  else if shop.isIssued k facet then some (some facet)
  else none

/-- (b) A facet the shop did not issue is refused by `acceptFacet`. -/
theorem forged_facet_refused (shop : Shop) (k : FacetKind) (facet : CapName)
    (slot : Option CapName) (h : shop.isIssued k facet = false) :
    acceptFacet shop k facet slot = none := by
  cases slot <;> simp [acceptFacet, h]

/-- An issued facet is accepted into an empty slot. -/
theorem issued_facet_accepted (shop : Shop) (k : FacetKind) (facet : CapName)
    (h : shop.isIssued k facet = true) :
    acceptFacet shop k facet none = some (some facet) := by
  simp [acceptFacet, h]

/-- A slot is write-once: a second `acceptFacet` cannot replace the facet. -/
theorem slot_write_once (shop : Shop) (k : FacetKind) (facet current : CapName) :
    acceptFacet shop k facet (some current) = none := by
  simp [acceptFacet]

/-!
## Consumer-side mint guard and provisioning endpoint

T1 no longer sees T3's buffer cell, so the `sin > surplus` recapitalisation
check cannot live inside `MintFacet`.  It is a pre-effect guard on every mint
consumer: T2's `VaultBook.mint` and T4's `PSM.buyStable` check it before calling
the facet.  T2's provisioning endpoint is the published `VaultAccept` slot
owner; `VaultBook` and `LiquidationEngine` are call targets that read the slot.
-/

/-- A mint consumer's local buffer view.  The guard runs before the facet call. -/
structure MintConsumer where
  sin : Nat
  surplus : Nat
  deriving Repr

/-- Model a consumer mint: the recapitalisation guard is checked first, then
the mint facet is called.  The facet itself has no buffer access. -/
def MintConsumer.mint (consumer : MintConsumer) (amount : Nat) :
    Option (MintConsumer × Nat) :=
  if consumer.sin ≤ consumer.surplus then some (consumer, amount) else none

/-- A consumer with `sin > surplus` refuses before any mint effect. -/
theorem mint_consumer_refuses_recapitalise (consumer : MintConsumer) (amount : Nat)
    (h : consumer.surplus < consumer.sin) : consumer.mint amount = none := by
  simp [MintConsumer.mint, Nat.not_le.mpr h]

/-- Every successful consumer mint saw `sin ≤ surplus` before the effect. -/
theorem mint_consumer_recap_pre_effect (consumer : MintConsumer) (amount : Nat)
    (consumer' : MintConsumer) (paid : Nat)
    (h : consumer.mint amount = some (consumer', paid)) :
    consumer.sin ≤ consumer.surplus := by
  unfold MintConsumer.mint at h
  split at h
  · rename_i hg
    exact hg
  · contradiction

/-- T2's provisioning endpoint.  It owns the private write-once slot; the
`VaultBook` and `LiquidationEngine` contracts only read it. -/
structure VaultAccept where
  slot : Option CapName
  deriving Repr

/-- Install a delivered facet into the `VaultAccept` slot. -/
def VaultAccept.install (accept : VaultAccept) (shop : Shop) (k : FacetKind)
    (facet : CapName) : Option VaultAccept :=
  match acceptFacet shop k facet accept.slot with
  | some installed => some { slot := installed }
  | none => none

/-- A filled `VaultAccept` slot is never replaced. -/
theorem vault_accept_slot_write_once (accept : VaultAccept) (shop : Shop)
    (k : FacetKind) (facet : CapName) (h : accept.slot.isSome = true) :
    accept.install shop k facet = none := by
  cases hs : accept.slot with
  | none => simp [hs] at h
  | some current => simp [VaultAccept.install, acceptFacet, hs]

/-- `VaultBook` and `LiquidationEngine` are call targets, not slot owners. -/
theorem call_target_is_not_vault_accept (owner : String)
    (h : owner = "VaultBook" ∨ owner = "LiquidationEngine") :
    owner ≠ "VaultAccept" := by
  rcases h with rfl | rfl <;> simp

/-!
## Auth sets and the settlement return shape

Rotation covers the four T1 auths, four T3 auths, two T4 auths, T2's
`LiquidationAuthLedger` and the market/directory auths; every set has its own
`auth:<currency>:<kind>` domain.  `SettlementFacet.settle` returns either
`(true, principal, Nil)` or `(true, principal, interestPay)`; T2 deposits
`interestPay` through `BufferOperatorFacet`.
-/

/-- Every auth set the Governor rotation model must cover. -/
inductive AuthSet where
  | issuerMint
  | issuerBurn
  | issuerSettle
  | issuerCustody
  | bufferDeposit
  | bufferPay
  | bufferCover
  | savingsNotify
  | psmMint
  | psmBurn
  | liquidation
  | market
  | directory
  deriving DecidableEq, Repr

/-- The unique Governor domain of each auth set. -/
def AuthSet.domain : AuthSet → String
  | .issuerMint => "auth:<currency>:mint"
  | .issuerBurn => "auth:<currency>:burn"
  | .issuerSettle => "auth:<currency>:settle"
  | .issuerCustody => "auth:<currency>:custody"
  | .bufferDeposit => "auth:<currency>:buffer-deposit"
  | .bufferPay => "auth:<currency>:buffer-pay"
  | .bufferCover => "auth:<currency>:buffer-cover"
  | .savingsNotify => "auth:<currency>:savings-notify"
  | .psmMint => "auth:<currency>:psm-mint"
  | .psmBurn => "auth:<currency>:psm-burn"
  | .liquidation => "auth:<currency>:liquidation"
  | .market => "auth:market"
  | .directory => "auth:directory"

def t1AuthSets : List AuthSet :=
  [.issuerMint, .issuerBurn, .issuerSettle, .issuerCustody]

def t3AuthSets : List AuthSet :=
  [.bufferDeposit, .bufferPay, .bufferCover, .savingsNotify]

def t4AuthSets : List AuthSet := [.psmMint, .psmBurn]

def otherAuthSets : List AuthSet := [.liquidation, .market, .directory]

/-- Four T1, four T3, two T4, one liquidation and two market/directory sets. -/
theorem auth_set_counts :
    t1AuthSets.length = 4 ∧ t3AuthSets.length = 4 ∧ t4AuthSets.length = 2 ∧
      otherAuthSets.length = 3 := by
  decide

/-- Every auth set has a distinct rotation domain. -/
theorem auth_domains_nodup :
    ((t1AuthSets ++ t3AuthSets ++ t4AuthSets ++ otherAuthSets).map AuthSet.domain).Nodup := by
  decide

/-- The settlement arm returns `(true, principal, Nil)` or
`(true, principal, interestPay)`. -/
inductive SettlementReturn where
  | noInterest (principal : Nat)
  | withInterest (principal : Nat) (interestPay : Nat)
  deriving DecidableEq, Repr

namespace SettlementReturn

def principal : SettlementReturn → Nat
  | noInterest p => p
  | withInterest p _ => p

/-- The payment T2 sends to `BufferOperatorFacet.deposit`, if any. -/
def bufferPayment : SettlementReturn → Option Nat
  | noInterest _ => none
  | withInterest _ pay => some pay

def t2Action : SettlementReturn → String
  | noInterest _ => "no-buffer"
  | withInterest _ _ => "buffer-deposit"

end SettlementReturn

/-- A settlement with interest routes the interest payment to the buffer. -/
theorem settlement_interest_routes_to_buffer (principal interestPay : Nat) :
    (SettlementReturn.withInterest principal interestPay).bufferPayment =
      some interestPay := by
  simp [SettlementReturn.bufferPayment]

/-- A settlement without interest routes no buffer payment. -/
theorem settlement_clean_routes_nothing (principal : Nat) :
    (SettlementReturn.noInterest principal).bufferPayment = none := rfl

/-- Every settlement reply has exactly one of the two documented shapes. -/
theorem settlement_return_shape (reply : SettlementReturn) :
    reply = .noInterest reply.principal ∨
      ∃ principal interestPay, reply = .withInterest principal interestPay := by
  cases reply <;> simp [SettlementReturn.principal]

/-!
## Rotation through the Governor

Each auth is a value in a per-auth cell owned by the term's `AuthLedger`.  A
facet holds the cell identity, not the value, and reads the current value per
call.  Rotation uses the published `Governor@"authorize"` choke point
(`domain, nonce, action, argsHash, sigs`), not an internal admin contract:
`domain` is unique per auth set (`auth:<currency>:<kind>`), `action` is
`"rotate"`, and the threshold signatures cover `argsHash`.  The ledger creates a
fresh auth internally, so no new auth is supplied by the caller.  `rotate`
replaces the value and bumps the revision.  The facet keeps working; a caller
presenting the old value is refused.
-/

/-- One auth cell. -/
structure AuthCell where
  current : CapName
  rev : Nat

/-- The live auth cells, indexed by cell identity. -/
structure Env where
  cell : Nat → AuthCell

/-- The published Governor state for one auth domain.  `authorize` is the only
rotation gate; there is no separate AuthAdmin contract. -/
structure Governor where
  domain : String
  nonce : Nat
  action : String
  argsHash : CapName
  threshold : Nat
  approvals : Nat
  deriving Repr

/-- The five signed values a rotation presents to `Governor.authorize`. -/
structure RotationRequest where
  domain : String
  nonce : Nat
  action : String
  argsHash : CapName
  sigs : Nat

/-- Governor.authorize: the domain, nonce, action and args hash must match the
scheduled rotation and the signature count must reach the threshold. -/
def Governor.authorized (gov : Governor) (domain : String) (nonce : Nat)
    (action : String) (argsHash : CapName) (sigs : Nat) : Bool :=
  decide (domain = gov.domain ∧ nonce = gov.nonce ∧ action = gov.action ∧
    argsHash = gov.argsHash ∧ sigs ≥ gov.threshold)

/-- Root-authorized rotation: replace the value and bump the revision. -/
def rotate (env : Env) (id : Nat) (newAuth : CapName) : Env :=
  { cell := fun i =>
      if i = id then { current := newAuth, rev := (env.cell i).rev + 1 }
      else env.cell i }

/-- A rotation is reachable only through `Governor.authorize`. -/
def rotateVia (env : Env) (gov : Governor) (id : Nat) (newAuth : CapName)
    (req : RotationRequest) : Option Env :=
  if gov.authorized req.domain req.nonce req.action req.argsHash req.sigs then
    some (rotate env id newAuth)
  else none

/-- A rotation without a matching Governor authorization is refused. -/
theorem rotation_requires_governor (env : Env) (gov : Governor) (id : Nat)
    (newAuth : CapName) (req : RotationRequest)
    (h : gov.authorized req.domain req.nonce req.action req.argsHash req.sigs = false) :
    rotateVia env gov id newAuth req = none := by
  simp [rotateVia, h]

/-- A matching authorization performs exactly the cell rotation. -/
theorem authorized_rotation_keeps_facet (env : Env) (gov : Governor) (id : Nat)
    (newAuth : CapName) (req : RotationRequest)
    (h : gov.authorized req.domain req.nonce req.action req.argsHash req.sigs = true) :
    rotateVia env gov id newAuth req = some (rotate env id newAuth) := by
  simp [rotateVia, h]

/-- The authorization binds the domain and the `rotate` action. -/
theorem authorized_domain_action (gov : Governor) (req : RotationRequest)
    (h : gov.authorized req.domain req.nonce req.action req.argsHash req.sigs = true) :
    req.domain = gov.domain ∧ req.action = gov.action := by
  have hc := of_decide_eq_true h
  exact ⟨hc.1, hc.2.2.1⟩

/-- `AuthLedger.check`: a presented auth is accepted only if it equals the
cell's current value. -/
def ledgerCheck (env : Env) (id : Nat) (auth : CapName) : Bool :=
  decide (auth = (env.cell id).current)

/-- A facet names the cell it reads, never the value. -/
structure Facet where
  kind : FacetKind
  cellId : Nat

/-- The value a facet uses on its next call: read fresh from its cell. -/
def facetReadsCurrent (facet : Facet) (env : Env) : CapName :=
  (env.cell facet.cellId).current

/-- (d) Rotation preserves the facet: it still reads a live auth, and after
rotation that auth is the new value. -/
theorem rotation_preserves_facet (env : Env) (facet : Facet) (newAuth : CapName) :
    facetReadsCurrent facet (rotate env facet.cellId newAuth) = newAuth := by
  simp [facetReadsCurrent, rotate]

/-- (d) Rotation refuses the old auth. -/
theorem rotation_refuses_old (env : Env) (id : Nat) (old newAuth : CapName)
    (hcell : (env.cell id).current = old) (hne : newAuth ≠ old) :
    ledgerCheck (rotate env id newAuth) id old = false := by
  unfold ledgerCheck
  simp only [rotate, hcell]
  exact decide_eq_false (fun h => hne h.symm)

/-- (d) The new auth is accepted after rotation. -/
theorem rotation_accepts_new (env : Env) (id : Nat) (newAuth : CapName) :
    ledgerCheck (rotate env id newAuth) id newAuth = true := by
  simp [ledgerCheck, rotate]

/-- A Governor-authorized rotation refuses the old auth and keeps the facet
live: the facet reads the rotated cell, and `ledgerCheck` rejects the old
value. -/
theorem authorized_rotation_refuses_old (env : Env) (gov : Governor) (id : Nat)
    (old newAuth : CapName) (req : RotationRequest)
    (hauth : gov.authorized req.domain req.nonce req.action req.argsHash req.sigs = true)
    (hcell : (env.cell id).current = old) (hne : newAuth ≠ old) :
    ∃ env', rotateVia env gov id newAuth req = some env' ∧
      ledgerCheck env' id old = false := by
  refine ⟨rotate env id newAuth, ?_, ?_⟩
  · exact authorized_rotation_keeps_facet env gov id newAuth req hauth
  · exact rotation_refuses_old env id old newAuth hcell hne

/-- A Governor-authorized rotation accepts the new auth. -/
theorem authorized_rotation_accepts_new (env : Env) (gov : Governor) (id : Nat)
    (newAuth : CapName) (req : RotationRequest)
    (hauth : gov.authorized req.domain req.nonce req.action req.argsHash req.sigs = true) :
    ∃ env', rotateVia env gov id newAuth req = some env' ∧
      ledgerCheck env' id newAuth = true := by
  refine ⟨rotate env id newAuth, ?_, ?_⟩
  · exact authorized_rotation_keeps_facet env gov id newAuth req hauth
  · exact rotation_accepts_new env id newAuth

/-- Rotation changes only the named cell. -/
theorem rotation_other_cell (env : Env) (id other : Nat) (newAuth : CapName)
    (h : other ≠ id) : (rotate env id newAuth).cell other = env.cell other := by
  simp [rotate, h]

end Rholphin.Linear
