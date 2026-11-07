# Object-capability audit of r-cash

Status: 2026-11-07. Scope: the v0.4 deploy sources under
`contracts/src/deploy/v3/`, the flow specifications, the Lean model, and the
capability gates. The adversarial half of this exercise is in
[OCAP-REDTEAM.md](OCAP-REDTEAM.md); the mechanical gate is
`tools/check_capabilities.py`.

## 1. What is being measured

R-Cash's authority model is written down in [00-CALCULUS.md](00-CALCULUS.md):
authority is an unforgeable `new`-bound name held in a closure. A name supplied
by an arbitrary caller is a sink facet, a payment or a reply channel, never
authority. A published bundle must not capture a registry-resolved capability.
A privileged arm must compare its authority argument against a name it already
holds. The runtime has no provenance check (N6), so the model is enforced by
discipline, a mechanical gate and the empirical block-boundary tests.

| Provenance | Meaning | Allowed as authority |
|---|---|---|
| Fresh | created by `new` in the component | yes |
| Installer | pinned by the bootstrap/Root | yes |
| Issuer | returned by an authority in a documented arm | yes |
| Caller | supplied by an arbitrary caller | **no** (sink facet/payment/reply only) |

## 2. Rubric and grades

Grades are after the fixes in this branch. The `before` column is the grade the
walk assigned to merged `main` (commit `baf32cd` + the match rewrite).

| ID | Criterion | Before | After |
|---|---|---|---|
| O1 | unforgeability: authority is `new`-bound, never derived from data | A | A |
| O2 | provenance: every authority use has Fresh/Installer/Issuer provenance | B | A− |
| O3 | sink facets: caller names are receive-only, never authority | B+ | A |
| O4 | confinement: caps stay in the closure that needs them | C | B |
| O5 | least authority: per-instance, per-operation caps | C | C |
| O6 | no confused deputy: no authority exercised for an unauthenticated caller | B− | B+ |
| O7 | attenuation: delegated caps are narrowed to op/amount/scope | D | C |
| O8 | revocation/rotation: a leaked or stale cap can be retired | D | C+ |
| O9 | replay/domain separation: signed authority binds domain/nonce/deadline/action | C | C |
| O10 | no capability leakage via replies, attestations, views or bundles | B | B+ |
| O11 | fail-closed authority: a failed check cannot fall through to success | B | A |
| O12 | negative-test coverage: every authority boundary has an adversarial test | C | B |

## 3. Authority inventory

| Authority | Scope | Provenance | Attenuation | Rotation |
|---|---|---|---|---|
| `mintAuth`, `burnAuth`, `custodyAuth`, `liquidationAuth`, `settlementAuth`, `psmMintAuth`, `psmBurnAuth`, `bufferDepositAuth`, `bufferPayAuth`, `bufferCoverAuth`, `savingsNotifyAuth` | per stablecoin deploy, unlimited operation authority | Fresh | none | none |
| `marketAuth` | all MarketDirectory/MarketIndex/MarketFactory writes | Fresh | none | none |
| `directoryAuth` | CurrencyRegistry/StablecoinDirectory writes | Fresh | none | none |
| `rootAuthorize` | governance choke point (threshold signatures) | Fresh | threshold | Root.rotate for component URIs |
| per-account `proof` | one owner, all currencies; opens the owner's vaults | Fresh | one owner | none |
| per-vault `auth` | one vault; deposit/mint/withdraw/repay/liquidate | Fresh | one vault | **rotate** (new) |
| `lpMint`/`lpBurnFacet`/`lockPurse` | one pool / one seed lock | Fresh | one pool | none |
| caller facets and payments | sink-only (`deposit`), consumed on use | Caller | sink | n/a |
| registry-resolved names | resolved per arm and used immediately | Installer | per arm | Root.rotate |

The eleven issuer auths are captured in the closure of every stablecoin
component bundle that references them (see the `G-CAP-BUNDLE` metrics). That is
the authority-co-location finding OCAP-08; it is a partitioning issue, not a
leak: a bundle is opaque and a caller cannot rebind the free names.

## 4. Findings

Severity is the walk's assessment. `Fixed` means the branch changes the code and
has an executed test; `Baselined` means the gate records the finding and a
refactor is deferred; `Accepted` means the model explicitly accepts it.
`Model` means the multi-term artifact and proof exist on this branch but the
deploy-source migration and its devnet runs are not merged; it is not a fix.

| ID | Finding | Severity | Status |
|---|---|---|---|
| OCAP-01 | `Root.resolve` status arms inverted: `"retired"` succeeded and every active component refused | Critical | **Fixed** (commit `b426c72`; fresh install resolves every key) |
| OCAP-02 | `TradabilityGate.admit` inverted: `"active"` refused, every swap failed | High | **Fixed** (`b426c72`; RT-11b) |
| OCAP-03 | `account.vaultOpen` forwarded the owner's proof to a caller-supplied `vaultUri` | Critical | **Fixed** (registry-pinned vault; RT-03) |
| OCAP-04 | Raw issuer auths are authority-as-argument; one leak is unlimited mint/burn/custody/liquidation | High | **Model**: multi-term facets and the P5/P7 shop are specified and proved (`Linear.Provisioning`); the five-term deploy migration is pending integration |
| OCAP-05 | Account proof stored in the account registry entry and in the returned bundle | High | **Fixed** (dedicated `proofState`; the account closure still holds the proof it needs) |
| OCAP-06 | No attenuation: issuer authority is all-or-nothing | High | **Model**: `Linear.Prov` proves facet-kind attenuation (`facet_store_scope`, foreign-kind/auth rejection); the facet terms are pending integration |
| OCAP-07 | No revocation for per-vault auth, issuer auth, `marketAuth`, `directoryAuth` | Medium | **Partial**: `VaultBook.rotate` added (RT-13); issuer/market/directory rotation is specified, proved (`Linear.Provisioning`) and modelled (`AuthRotation.tla`); the rotation arms and RT-17 are pending integration |
| OCAP-08 | Authority co-location: each published stablecoin bundle carries a subset of the currency's authority | Medium | **Model**: the five-term split and facet bundles close over no raw auth; `G-CAP-BUNDLE` gains an annotated bare-name-slot exception. The deploy migration is pending integration |
| OCAP-09 | Signed preimages use `toString()`/`"|"` instead of the canonical Codec | High | **Model**: the provisioning and rotation preimages bind domain/action/issuer/consumer/kind/nonce/deadline; `G-CAP-PROVISION` and RT-06 are added. The 14 legacy sites and the canonical rewrite are pending integration |
| OCAP-10 | `registerExternal` trusts the adapter's self-reported brand/issuer | Medium | Open |
| OCAP-11 | `register`/`registerExternal` do not require the submitter to be the sponsor | Medium | Open |
| OCAP-12 | `LiquidityLock.fund` is permissionless; activation does not bind funder/beneficiary to the sponsor | Medium | Open; the RT-12 scenario is written but unrun |
| OCAP-13 | PSM sell floor `stableDebt - amount + maxSupply >= 0` looked like an over-redemption bug | Medium | **Not a defect**: SPEC §11 and the flow define it as the negative-debt floor; the comment was reconciled |
| OCAP-14 | `check_captures.py` blind spots: no `rs!` publications, narrow bundle shapes | Medium | Mitigated by `check_capabilities.py`; captures still 0 findings |
| OCAP-15 | G-FACET is suffix-based and only checks a literal first argument | Medium | Mitigated by `G-CAP-AUTH` (every authority parameter) |
| OCAP-16 | Ambient `deployerId` authority in AccountGate; the account bundle is public | Medium | Accepted (the deployer identity is the authority; a shared bundle cannot act) |
| OCAP-17 | No Lean `Prov`; I20 was tool-evidenced only | Low | **Fixed**: `Rholphin.Linear.Prov` proves `caller_never_stored`, `authority_use_requires_provenance`, `bundle_no_registry_cap`, and (this branch) the facet-kind attenuation lemmas; I20 is covered |
| OCAP-18 | `TransferContract` carries the escrowed payment and both facets | Low | Accepted (claim/refund are gated; the registry entry is a bearer object by design) |
| OCAP-19 | Claim `secretHash` is not bound to the transfer id/recipient/domain | Low | Open |

## 5. What changed in this branch

1. **Restored the dispatches** (`b426c72`). The match-review rewrite inverted
   exactly four single-tag dispatches: `Root.resolve` retired/active,
   `TradabilityGate.admit` active, the market record draft transition, and the
   `MarketIndex.stage` record status. All four are corrected and have
   behavioural vectors (RT-11a/RT-11b and the flow specs).
2. **Split the pool term** (`605a33c`). The pre-existing `51_pool` term exceeded
   the node's `MAX_PARSE_DEPTH = 128`; the lock factory is now `51_lock` and the
   swap arm is decomposed into `swapCalc`/`swapValue`/`swapExec`. All 20 built
   terms parse and a fresh install reaches `09_identity`.
3. **Pinned and confined the account proof** (`796d283`). `vaultOpen(dId, code)`
   resolves the currency registry through Root and sends the proof only to the
   registry-pinned vault; a hostile URI passed as the code returns
   `(false, "no currency")`. The proof moved from the account registry entry to
   a dedicated `proofState` cell.
4. **Added the capability gate** (`4c492e1`). Rules `G-CAP-AUTH`, `G-CAP-STORE`,
   `G-CAP-LEAK`, `G-CAP-DOMAIN`, `G-CAP-REGISTRY`, `G-CAP-BUNDLE`; baseline 52
   (38 bundle metrics + 14 domain-separation sites), wired into `formal-check`
   and `pre-devnet-check`.
5. **Added the red-team suite** (`32863c3`) and **per-vault rotation**
   (`56543c9`).
6. **Added the provenance model** (`Rholphin/Linear/Prov.lean`): the provenance
   inductive, the store/call/bundle rules and the three theorems behind I20.
   `check_lean` now audits 74 declarations and I20 moves from `tool` to
   `covered`.

## 6. Why the facet refactor was not applied

The approved plan proposed four holder-scoped facets (`VaultAuthority`,
`PsmAuthority`, `BufferAuthority`, `SavingsAuthority`). The walk shows that in
this architecture the facets would not attenuate anything: every stablecoin
component is defined in one deploy term and captures the raw auths directly
from the enclosing `new` scope. A facet contract added in that same scope would
see the same auths, and every sibling that can call the facet can already call
the component. The exposure is the bundle closure, not the call argument.

The structural changes that do reduce blast radius are the ones applied:
confinement of the account proof, registry-pinning of `vaultOpen`, and
rotation of the per-vault capability. The remaining reduction requires moving
the components into separate deploy terms so the facet's closure is genuinely
narrower than its callers'; that is a deployment-architecture change, not a
facet rename, and it is recorded as OCAP-04/06 rather than pretended to be
fixed. `31_stablecoin` is at 69 contracts (68 + rotation) against a 69
override; a split is the prerequisite for any further contract-level work.

## 7. Gate

```sh
make capability-check          # tools/check_capabilities.py --check
python3 tools/check_capabilities.py --strict   # zero-finding target
```

The baseline is a ratchet: new findings fail `formal-check`, and the two
recorded classes are the intended refactor backlog (OCAP-08 bundle partitioning,
OCAP-09 canonical preimages). `G-CAP-BUNDLE` is a design metric with a
justification per bundle; the other five rules describe hard constraints.

## 8. Verification

Executed on a devnet recreated from an empty volume (`make down` then `make
devnet`) and installed with `harness/install_testnet.py` from this branch. A
recovery read with a root-only state resolved all 18 steps again, so the
install is reproducible from the registry alone.

| Check | Result |
|---|---|
| All 20 built terms parse under the node parser (`MAX_PARSE_DEPTH = 128`) | pass |
| Fresh install: 18/18 Root keys resolved (incl. `component:liquidity-lock-factory`, `component:pool-template`, `component:account-factory`) | pass |
| `harness/unit_ocap.py` (12 checks, including RT-03 and RT-13) | pass |
| `make unit-stablecoin` (issuer, listing, savings, ops through the registry-pinned vault) | pass |
| `make unit-market` (pool template, lock factory, decomposed swap) | pass |
| `make unit-v3 unit-feed unit-hub unit-timelock unit-transfer unit-savings unit-psm unit-liquidation` | pass |
| `ACCOUNTS_KEY=key19 make unit-accounts`, `INTEREST_KEY=key18 make unit-interest` | pass (the defaults share a key with `unit-transfer`/`unit-psm`; see below) |
| `make spec-check check-flows check-trace capability-check match-check arm-vectors lean-check` | pass |
| `tools/check_captures.py --check` | 0 findings |
| `tools/check_capabilities.py --check` | 52 baselined (38 `G-CAP-BUNDLE`, 14 `G-CAP-DOMAIN`) |

The default `business` (accounts) and `key16` (interest) are also used by
`unit-transfer` and `unit-psm`, so a suite run out of `make unit-all` order sees
a non-empty purse or vault. The env overrides let each suite pick an unused key;
in the canonical order the defaults pass.

## 9. Residual risks

- Issuer auths and `marketAuth`/`directoryAuth` have no rotation. A leaked raw
  auth cannot be retired without redeploying the currency/market system.
- Signed preimages are not canonical (OCAP-09); the preimages bind domain and
  action, but not all bind a deadline, and the encoding is ambiguous for
  strings containing `|`.
- `registerExternal` does not cross-check the adapter's brand (OCAP-10); a
  malicious adapter can list an asset whose issuer it does not control.
- The account proof is still a bearer token inside `bundle+{*account}`; the
  bundle is opaque, but anyone given the account bundle can call its arms, and
  the arms are gated by the deployer identity rather than by the bundle itself
  (OCAP-16).
- The Lean model abstracts the proof and the per-vault auth; the flow specs and
  the red-team suite are the evidence for the access-control transitions.

## 10. Multi-term verification (2026-11-07)

The five-term split and the P5/P7 provisioning protocol are recorded in
[MULTI-TERM.md](MULTI-TERM.md). This branch adds the static verification layer;
the deploy-source migration and every devnet run remain integration work.

**Lean** (`spec/lean/Rholphin/Linear/Provisioning.lean`, `Prov.lean`):

- `nonce_cannot_provision_twice` — a consumed nonce cannot provision twice;
- `provision_requires_pinned_shop`, `issuer_shop_cannot_issue_buffer`,
  `buffer_shop_cannot_issue_mint` — per-term shops, each consumer mapping a kind
  to its pinned shop (`VaultAccept` owns T2's slot);
- `provision_refusal_rolls_back` — a consumer refusal rolls the nonce back;
- `provision_returns_no_cap` — the caller-visible reply exposes no capability;
- `provision_routes_facets_to_consumer` — the requested facets are delivered to
  the pinned consumer, not the caller;
- `forged_facet_refused` / `slot_write_once` / `vault_accept_slot_write_once` —
  a forged or wrong-shop facet is refused, and a filled slot is never replaced;
- `mint_consumer_refuses_recapitalise`, `mint_consumer_recap_pre_effect` — the
  `sin > surplus` check is a pre-effect guard on each mint consumer, not the
  facet;
- `settlement_interest_routes_to_buffer`, `settlement_return_shape` — the
  `SettlementFacet` return shapes and the buffer deposit of `interestPay`;
- `rotation_preserves_facet`, `rotation_refuses_old`, `rotation_accepts_new`,
  `rotation_requires_governor`, `authorized_rotation_refuses_old` / `_accepts_new`
  — rotation through `Governor@"authorize"` keeps the facet live, refuses the
  old auth and accepts the new one; `auth_set_counts` covers the four T1, four
  T3, two T4, liquidation and market/directory domains;
- `facet_store_scope`, `facet_store_rejects_foreign_kind`,
  `facet_store_rejects_foreign_auth`, `mint_facet_cannot_store_burn_auth`,
  `burn_facet_cannot_store_mint_auth`, `burn_facet_call_carries_payment` — facet
  attenuation and the payment-carrying ABI.

All are in `Rholphin/Audit.lean`; `check_lean.py` reports 107 axiom audits with no
`sorryAx` or project-local axiom.

**TLA+**: `Provisioning.tla` (per-term shops, reserve/confirm, replay, forged
grant, `VaultAccept`, recap guard, settlement routing) and `AuthRotation.tla`
(old-refused/new-accepted through `Governor@"authorize"`, catalogue covering the
liquidation ledger); `CapabilityProvenance.tla` gains facet attenuation and the
no-facet-publication rule. TLC was run locally on 2026-11-07: 5,760, 20 and 32
distinct states respectively, all invariants hold.

**Gate**: `G-CAP-FACET` (no facet name in replies, attestations or published
data maps), `G-CAP-PROVISION` (sponsor/issuer/consumer/kind/nonce/deadline
binding, nonce consumed before the consumer call, `fail()` on refusal) and the
annotated bare-name-slot exception for `G-CAP-BUNDLE`. The report-mode run is 52
baselined findings, unchanged.

**Not run**: RT-01, RT-04, RT-05, RT-06, RT-12 and RT-14–RT-17 are written as
scenarios and, where the surface exists, as `unit_ocap.py` probes. This branch
has no devnet and no integrated five-term install, so none is recorded as
passing. RT-06, RT-12 and RT-14–RT-17 are pending integration.
