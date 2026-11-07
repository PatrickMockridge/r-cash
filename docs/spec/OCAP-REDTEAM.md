# Capability red-team exercise

Status: 2026-11-07. The audit is in [OCAP-AUDIT.md](OCAP-AUDIT.md). This file
records the threat model, the scenarios, and the results actually observed on
the local devnet. The repeatable driver is `harness/unit_ocap.py`.

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
| RT-01 | Call each issuer arm with a fresh name: `mint`, `burn`, `settle`, `custody`, `liquidate`, PSM, buffer, savings | refused, fail-closed | **Written, unrun**: `ocap_issuer_fresh_names.rho` (T1 mint/custody) and `ocap_buffer_fresh_names.rho` (T3 cover), with `unit_ocap` probes. Needs the integrated five-term install |
| RT-02 | Call `MarketDirectory.bind` with a fresh name as the auth | refused | **Executed**: `(False, "bad directory authority")` |
| RT-03 | Open an account, pass a hostile `vaultUri`, capture the proof, replay it | refused; the hostile contract is never called | **Executed**: `(False, "no currency")`, hostile vault not reached |
| RT-04 | Pass a caller facet with a `withdraw`/callback arm; assert only `deposit` is called | no non-sink call | **Written, unrun**: `ocap_caller_facet_sink.rho`; the hostile facet records a `withdraw` call and the claim must leave it unset |
| RT-05 | Use account A's proof/account bundle on B's vault, wrong deployerId | refused | **Written, unrun**: `ocap_cross_owner.rho`; expected `(False, "not owner")` |
| RT-06 | Replay admin/market/feed/currency signatures; cross-domain substitution | refused; canonical encoding | **Written, unrun**: `ocap_canonical_preimage.rho` submits a `rcash:provision:v2` signature to the v1 T1 issuer shop. The canonical rewrite and 14 legacy sites are pending integration |
| RT-07 | Publish/resolve a bundle, cross a block boundary, call it; introspect | persists; cannot destructure | Empirical, by `install_testnet.py`'s signed reads after every step |
| RT-08 | Pause/delist a vault/market/issuer, then use it | refused | Market pause/delist is exercised by `unit_market`; currency pause by `unit_stablecoin` |
| RT-09 | Substitute a caller URI for a pinned component | refused | **Executed** as RT-03; the pinned URI is the registry's `vaultUri` |
| RT-10 | Wrong secret, foreign refund, claim/refund race, opId replay | refused/terminal | Exercised by `unit_transfer` |
| RT-11 | `Root.resolve` after `deprecate`; `TradabilityGate` with `active` | deprecate refuses; active admits | **Executed**: active `(True, uri, version)`, unknown `(False, "unknown component")`, stale `(False, "stale")`, gate `(True, Nil)` |
| RT-12 | Lock funding/activation front-run with a different funder/beneficiary | refused | **Written, unrun**: `ocap_lock_frontrun.rho`; OCAP-12's funder binding is pending integration |
| RT-13 | Rotate a vault auth, then use the old auth | rotated-out auth refused | **Executed** below |
| RT-14 | Provision a facet with a non-sponsor signature (or a different issuer/consumer) | refused; no nonce consumed, no slot written | **Written, unrun**: `ocap_unauthorised_provision.rho` (T1 issuer shop) and the `unit_ocap` probe. Pending integration |
| RT-15 | Call `acceptFacet` directly with a fresh name; replay a consumed provisioning nonce | forged facet refused; replay refused | **Written, unrun**: `ocap_forged_accept.rho` for the forged facet; the replay half needs the canonical `provision_payload` helper. Pending integration |
| RT-16 | Mint through T2's provisioned MintFacet, then trigger a downstream `1/0` | deploy aborts; issuer supply, slots and nonce roll back | **Written, unrun**: `ocap_cross_term_rollback.rho` calls `VaultBook.mint` after the consumer's `sin ≤ surplus` guard; the probe asserts the deploy error and compares `Stablecoin.supply`. Pending integration |
| RT-17 | Rotate an auth through `Governor@"authorize"`, then present a stale auth and call the facet | stale auth refused; new auth accepted; facet live | **Written, unrun**: `ocap_stale_auth.rho` calls `authorize(domain, nonce, "rotate", argsHash, sigs)` and then the ledger; the production ledger has no test-only `current` arm, so the scenario models the stale value as a fresh non-current name. Pending integration |

## 3. Results

The suite runs against a devnet installed from this branch. Each command is a
signed deploy; the assertion is on the reply.

```sh
python3 harness/unit_ocap.py
```

Recorded on a fresh devnet (`make RHOLO_DIR=/home/patrick/rholo-fixed down` then
`devnet`, a full `install_testnet.py` install, then `make unit-stablecoin` so a
V4T system is listed):

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

- RT-01, RT-04, RT-05, RT-06, RT-12 and RT-14–RT-17 are written as scenarios and
  `unit_ocap` probes but were **not run** on this branch: there is no integrated
  five-term devnet here. A written probe is not a pass. The static Lean/TLA
  layer proves the protocol obligations; the scenarios are the empirical test
  the integrator must run after the term merge.
- The negative issuer-arm tests (RT-01) exercise the arms that survive the
  five-term split. If an arm is removed entirely, the probe is silent rather
  than refused and the integrator must adjust the scenario, not record a pass.
- Signed-payload replay (RT-06) is open until the canonical Codec replaces the
  `toString()`/`"|"` preimages (OCAP-09); the provisioning payload is the first
  canonical instance.
- The lock front-run (RT-12) is open (OCAP-12) and needs a live unfunded lock
  plus an LP payment supplied out of band.
- RT-17 cannot reconstruct the old auth on-chain: the Phase 0 test-only
  `AuthLedger@"current"` arm is not production. The scenario checks that a
  non-current name is refused and that the facet still works; a true
  old-value replay needs a captured auth from `unit_stablecoin`'s provisioning
  path.
- A fresh install is the gate for the dispatch fixes; a stale install is not
  evidence. The results in §3 are from a fresh install of the pre-multi-term
  branch and do not cover RT-14–RT-17.
