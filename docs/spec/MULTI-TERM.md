# Multi-term stablecoin architecture

Status: 2026-11-07. Phase 0 go decision recorded below. This note is the
interface contract for the five-term split; `00-CALCULUS.md` carries the
normative rule amendments, `OCAP-AUDIT.md` the finding status.

## 1. Why the cluster splits

The audit established that in-term operation facets cannot attenuate: an auth
must be `new`-bound in the term that both checks and passes it, C3/S4 forbid a
published bundle closing over a registry-resolved capability, and L6 co-locates
the waterfall invariants. The reduction therefore requires separate deploy
terms whose published bundles close over narrower capabilities.

## 2. Terms and authority ownership

Authority follows the checker: a term owns the auths whose checks live in its
contracts.

| Term | File | Published components | Authority |
|---|---|---|---|
| T1 issuer | `31_issuer.rho` | `Stablecoin`, `CollateralCustody`, `AuthLedger`, `FacetShop` | `mintAuth`, `burnAuth`, `settlementAuth`, `custodyAuth` |
| T2 vault | `31_vault.rho` | `VaultBook`, `LiquidationEngine` | `liquidationAuth`, per-vault auths |
| T3 buffer/savings | `31_buffer_savings.rho` | `SavingsPool`, `SurplusBuffer`, `BufferFacetShop` | `bufferDepositAuth`, `bufferPayAuth`, `bufferCoverAuth`, `savingsNotifyAuth` |
| T4 PSM | `31_psm.rho` | `PegStabilityModule` | `psmMintAuth`, `psmBurnAuth` |
| T5 params | `31_params.rho` | `RiskParameters` | none |

Each auth is a value in a per-auth cell owned by that term's `AuthLedger`
(`mintAuthCell`, ...). A facet captures only the cells it needs and reads the
current value per call.

Rotation uses the published `Governor@"authorize"` choke point, not the
internal `rootAuthorize` helper (which cannot be reached from another term):

```
Governor!("authorize", domain, nonce, "rotate", argsHash, sigs, ret)
```

`domain` is unique per auth set (`auth:<currency>:<kind>`), and the ledger
creates a fresh auth internally — no new auth is supplied by the caller, so it
cannot leak. The ledger then takes and posts the cell, so the old value is
refused and the facet keeps working. `Governor` is resolved through
`component:governor` at arm entry, never captured in a bundle.

## 3. Facets

T1 creates `MintFacet`, `BurnFacet`, `SettlementFacet` and `CustodyFacet`; T3
creates `BufferOperatorFacet`. A facet is a service contract that holds only
its own auth cells and performs exactly its operation. It returns no
capability.

ABI:

The signatures mirror the privileged arms they wrap (a facet never invents a
different shape):

```
MintFacet!(   "mint",     @amount, ret)
BurnFacet!(   "burn",     payment, @maxAmount, ret)
SettlementFacet!("settle",payment, @principal, @interest, ret)
CustodyFacet!( "deposit", payment, ret)
CustodyFacet!( "withdraw",@amount, ret)
BufferOperatorFacet!("deposit", payment, ret)
BufferOperatorFacet!("paySavings", @amount, ret)
BufferOperatorFacet!("cover", @amount, ret)
```

The facet names are fresh names created by `new` in the owning term. They are
never published, returned in a reply, written to a data map, or logged.

## 4. Provisioning (P5 reserve/confirm, P7 intra-deploy grant)

`FacetShop` is published by T1. It binds the sponsor public key and its own
URI at creation, and exposes:

```
FacetShop!("provision", @consumerUri, @consumerTag, @kinds, @nonce,
           @deadline, @sponsorHex, @sig, ret)
FacetShop!("isFacet",   @kind, facet, ret)
```

Payload (production: `Codec@"canonical"` with schema `rcash:provision:v1` and
values `[issuerUri, consumerUri, consumerTag, kinds, nonce, deadline,
sponsor]`):

1. The caller presents a sponsor-signed payload. The shop verifies the sponsor
   equals its bound key and `sigOk` over the canonical hash; a wrong sponsor or
   signature is refused before any state change.
2. The shop consumes the nonce (one-shot) and `fail()`s on any later refusal,
   so the nonce and every slot roll back together.
3. The shop resolves the **pinned consumer URI from the payload itself**, never
   a caller-supplied URI, and calls
   `Consumer!("acceptFacet", kind, *Facet, nonce, deadline, ret)` in the same
   deploy. The facet name crosses as a process, not as data.
4. The consumer verifies the facet with the pinned `FacetShop.isFacet`, then
   writes it once to a private `new`-bound slot and refuses a second write.

A third party cannot obtain a facet: the sponsor signature gates delivery, the
shop picks the destination, and the facet is never exposed. The sponsor is the
same trust anchor that creates the currency today.

**Shops are per term.** T1 publishes the issuer `FacetShop`
(mint/burn/settle/custody); T3 publishes `BufferFacetShop` (buffer). A consumer
maps each kind to the shop pinned for it (`__ISSUER_SHOP_URI__` or
`__BUFFER_SHOP_URI__`) and verifies the received facet with that shop's
`isFacet`. T1 cannot issue a facet that lives in T3's closure, so a single
central shop is not an option.

## 5. The bare-name slot (the Phase 0 finding)

A name read out of a data map or `.get` is data and **cannot be used as a
channel**. The consumer slot therefore holds the facet as a bare name and every
operation calls it from a receive binding:

```rho
contract Consumer(@"acceptFacet", @kind, facet, @nonce, @deadline, ret) = {
  ... Shop!("isFacet", kind, *facet, *okCh) ...
  mintSlot!(*facet) | ret!((true, "provisioned"))
} |

contract Consumer(@"mint", @amount, ret) = {
  for (facet <<- mintSlot) { facet!("mint", amount, *ret) }
}
```

The slot is write-once, is captured only by the consumer's own `bundle` (C3
own-`new`), and is never returned. This is the L7 exception: a provisioned
issuer facet may live in a private bare-name slot, not in a data map.

## 6. Runtime waterfall

T2 coordinates T1 and T3 in one deploy with pinned callees. It validates on a
peek, performs the effects, then consumes and revalidates the vault state and
posts; any refusal after a value movement calls `fail()` (P3 + P6). No cell is
held across an await and no peeked snapshot is written after an await. T4
resolves `vaultUri` through `CurrencyRegistry` at arm entry for the pause read;
all effect callees are pinned placeholders. This breaks the T2/T4 URI cycle.

L6 is amended: one named atomic cluster may span pinned components within a
single deploy; the guarantee is restored at deploy end, and a failure aborts
the whole deploy. Cross-deploy operations use P5.

## 7. Registry listing

The eight slots stay: sc, custody, params, vault, liquidation, savings, PSM,
buffer. Each component gains `attest` returning
`{currency, paramsHash, sponsor, kind}`; `CurrencyRegistry.register`
cross-checks all eight and refuses a slot filled by the wrong kind.
`paramsUri` is bound to the signed `paramsHash`.

## 8. Phase 0 evidence

Throwaway terms (not merged) deployed on the devnet from this branch. The
prototype had one auth cell, one `MintFacet`, `FacetShop.provision`/`isFacet`,
a rotating `AuthLedger`, and a consumer with a bare-name slot. The sponsor was
the devnet deployer key. Recorded output:

```
ok consumer refuses before provisioning
ok forged facet refused
ok facet delivered across terms
ok facet mint works
ok supply after mint
ok replayed nonce refused
ok rotation refuses old and accepts new
ok facet survives rotation
ok supply after rotation
ok mintThenFail aborted the deploy
ok rolled-back supply unchanged
phase0 spike: all proofs passed
```

Metrics: issuer prototype 2,965 minified bytes / 8 contracts / grammar depth
34; consumer 1,372 bytes / 3 contracts / depth 22. Both parse under
`MAX_PARSE_DEPTH = 128`. The `AuthLedger@"current"` arm used to capture the old
auth on-chain is test-only and must not exist in production.

**Go.** All five proofs passed with no node change and within harness phlo and
timeout. Proceed with the five-term split.

## 9. Gate and model additions

- `G-CAP-FACET`: a facet name may not appear in a reply, attestation, published
  data map or state map.
- `G-CAP-PROVISION`: provisioning must verify a sponsor key bound at creation,
  bind issuer/consumer/kind/nonce/deadline, consume the nonce before the
  consumer call, and `fail()` on refusal.
- `G-CAP-BUNDLE`: a consumer bundle closing over a bare-name slot is an
  annotated exception; a bundle closing over a raw auth is a finding.
- Lean: `Linear/Provisioning.lean` proves the one-shot nonce, forged-facet
  refusal and no-capability-return; `Prov` proves facet-kind attenuation.
- TLA: `Provisioning.tla` (reserve/confirm, replay) and `AuthRotation.tla`
  (old-refused/new-accepted).
