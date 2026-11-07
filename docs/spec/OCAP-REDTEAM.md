# Capability red-team exercise

Status: 2026-11-07. The audit is in [OCAP-AUDIT.md](OCAP-AUDIT.md). This file
records the threat model, the scenarios, and the results actually observed on
the local devnet. The repeatable driver is `harness/unit_ocap.py`; the executed results are in §3.

## 1. Threat model

| Adversary | Capability it starts with | Goal |
|---|---|---|
| Unprivileged deployer | phlo only | mint, burn, settle, custody, liquidate, or register without authority |
| Holder of one legitimate cap | one account proof, one vault auth, one sink facet, or one payment | escalate to another account, another vault, or an issuer |
| Malicious component reachable by URI | a registry URI it can publish | capture a capability a caller sends it; be substituted for a pinned component |
| Relayer of signed payloads | a valid signature for one action | replay it, cross domains, or change the action |
| Governance participant | a share below the threshold | execute a schedule that did not reach the threshold |
| Compromised reporter | a feed submission key | post a price outside its authorization |

The runtime does not check provenance; the red-team exercise is the empirical
check that the code's discipline holds.

## 2. Scenarios

| ID | Scenario | Expected | Status |
|---|---|---|---|
| RT-01 | Call each issuer arm with a fresh name: `mint`, `burn`, `settle`, `custody`, `liquidate`, PSM, buffer, savings | refused, fail-closed | **Executed**: the privileged arms are absent from the published bundles; the issuer and buffer shops refuse a fresh facet (`false`) |
| RT-02 | Call `MarketDirectory.bind` with a fresh name as the auth | refused | **Executed**: `(False, "bad directory authority")` |
| RT-03 | Open an account, pass a hostile `vaultUri`, capture the proof, replay it | refused; the hostile contract is never called | **Executed**: `(False, "no currency")`, hostile vault not reached |
| RT-04 | Pass a caller facet with a `withdraw`/callback arm; assert only `deposit` is called | no non-sink call | **Executed**: the canonical opId claim is accepted; the hostile `withdraw` is never called |
| RT-05 | Use account A's proof/account bundle on B's vault, wrong deployerId | refused | **Executed**: foreign deployer id refused |
| RT-06 | Replay admin/market/feed/currency signatures; cross-domain substitution | refused; canonical encoding | **Executed**: cross-domain signature refused; `G-CAP-DOMAIN` is 0 |
| RT-07 | Publish/resolve a bundle, cross a block boundary, call it; introspect | persists; cannot destructure | Empirical, by `install_testnet.py`'s signed reads after every step |
| RT-08 | Pause/delist a vault/market/issuer, then use it | refused | Market pause/delist is exercised by `unit_market`; currency pause by `unit_stablecoin` |
| RT-09 | Substitute a caller URI for a pinned component | refused | **Executed** as RT-03; the pinned URI is the registry's `vaultUri` |
| RT-10 | Wrong secret, foreign refund, claim/refund race, opId replay | refused/terminal | Exercised by `unit_transfer` |
| RT-11 | `Root.resolve` after `deprecate`; `TradabilityGate` with `active` | deprecate refuses; active admits | **Executed**: active `(True, uri, version)`, unknown `(False, "unknown component")`, stale `(False, "stale")`, gate `(True, Nil)` |
| RT-12 | Lock funding/activation front-run with a different funder/beneficiary | refused | **Gated**: `ocap_lock_frontrun.rho` needs a live unfunded lock and an LP payment out of band. The funder/height binding is exercised by `unit_market` and the mesh seed locks |
| RT-13 | Rotate a vault auth, then use the old auth | rotated-out auth refused | **Executed** below |
| RT-14 | Provision a facet with a non-sponsor signature (or a different issuer/consumer) | refused; no nonce consumed, no slot written | **Executed**: non-sponsor provisioning refused |
| RT-15 | Call `acceptFacet` directly with a fresh name; replay a consumed provisioning nonce | forged facet refused; replay refused | **Executed (forged)**: a direct `acceptFacet` with a fresh name is refused. The replay half is gated on a canonical `provision_payload` helper in the probe |
| RT-16 | Mint through T2's provisioned MintFacet, then trigger a downstream `1/0` | deploy aborts; issuer supply, slots and nonce roll back | **Gated**: `ocap_cross_term_rollback.rho` needs an opened probe-owned vault (`RCASH_OCAP_VAULT_URI`). The Phase 0 spike proved cross-term rollback; `unit_liquidation` exercises the P6 waterfall |
| RT-17 | Rotate an auth through `Governor@"authorize"`, then present a stale auth and call the facet | stale auth refused; new auth accepted; facet live | **Gated**: the generic probe needs captured admin signatures. `unit_liquidation` executes the liquidation rotation (old refused, new accepted, facet live); `AuthRotation.tla` proves the rule |

## 3. Results

The suite runs against a devnet installed from this branch. Each command is a
signed deploy; the assertion is on the reply.

```sh
RCASH_OCAP_CONSUMER=<vault_accept_uri> python3 harness/unit_ocap.py
```

Recorded on a fresh devnet (`make down`, `make devnet`, `make keys`,
`make install --fresh`, the full `unit-all` matrix and `make mesh-install`):

```
ok root resolve active
ok root resolve active uri
ok root resolve unknown
ok root resolve stale
ok tradability active admits
ok market bind refuses a fresh auth
ok vaultOpen ignores a caller URI (substitution)
ok vaultOpen reports the registry lookup
ok vaultOpen did not reach the hostile vault
ok vault rotation succeeds
ok rotated-out auth is refused
ok rotated-in auth is not refused
ok RT-01 issuer shop refuses a fresh facet
ok RT-01 buffer shop refuses a fresh facet
ok RT-04 claim accepted through a sink facet
ok RT-04 hostile withdraw was never called
ok RT-05 foreign deployerId refused
ok RT-06 cross-domain signature refused
skip RT-12 lock front-run (written, unrun: set RCASH_OCAP_LOCK_URI and RCASH_OCAP_LP_ASSET)
ok RT-14 unauthorised provisioning refused
ok RT-15 forged acceptFacet refused
skip RT-15 provisioning replay (written, unrun: no canonical provision_payload helper or facet shop)
skip RT-16 cross-term rollback (written, unrun: set RCASH_OCAP_VAULT_URI; needs root/stablecoin/owner)
skip RT-17 stale auth after rotation (written, unrun: set RCASH_OCAP_CONSUMER and RCASH_OCAP_SIGS; needs governor/auth-ledger URIs)
ocap red-team: all checks passed
```

### RT-03 detail

The probe publishes a contract whose `open` arm answers `(true, "captured")`,
then passes that contract's registry URI as the `code` argument to
`account.vaultOpen`. Before the fix, `vaultOpen` resolved the caller's URI and
sent the owner's proof to it, returning `captured`. After the fix it resolves
`component:currency-registry`, reads the entry's `vaultUri` and only then opens
the vault; an unlisted `code` returns `(false, "no currency")` and the hostile
contract is never called.

The positive path is covered by `make unit-stablecoin`: the savings and ops
scenarios open the V4T vault by currency code and mint, repay and withdraw
against it.

### RT-13 detail

`VaultBook.rotate(ownerId, auth, newAuth)` is called with the auth returned by
`vaultOpen`; a fresh name is created in the same deploy. The old auth is then
refused (`bad vault auth`) and the new auth is not. The rotation leaves the
vault ledger unchanged.

## 4. Limits of this exercise

- RT-12, the RT-15 replay half, RT-16 and RT-17 are gated, not passing: they
  need a live unfunded lock and LP payment, a canonical provision-payload
  helper in the probe, an opened probe-owned vault, and captured admin
  signatures respectively. Their shared code paths are exercised by
  `unit_market`/the mesh seed locks, `unit_liquidation`'s rotation and
  waterfall, and the Phase 0 cross-term rollback spike.
- RT-01 probes the shop identity boundary, because the split removed the
  privileged arms from the published bundles; calling a removed arm hangs
  rather than refusing, so the probe tests `isFacet` instead.
- The shops return a strict boolean. A tagged `(true, false)` reply was the
  confused-deputy shape the consumers' `ok == false` test treated as success;
  the match baseline records the deliberate exception, and RT-15 covers the
  forged-facet boundary.
- Signed-payload replay is closed by the canonical codec: `G-CAP-DOMAIN` is 0
  and RT-06's cross-domain substitution is refused.
- A fresh install is the gate; the results above are from a fresh install of
  this branch, not a reused chain.
