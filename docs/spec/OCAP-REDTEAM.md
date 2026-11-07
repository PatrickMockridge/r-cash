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
| RT-01 | Call each issuer arm with a fresh name: `mint`, `burn`, `settle`, `custody`, `liquidate`, PSM, buffer, savings | refused, fail-closed | Not yet automated (issuer arms are exercised by the stablecoin suite's positive paths; the negative path is `RT-02`-shaped and is the next addition) |
| RT-02 | Call `MarketDirectory.bind` with a fresh name as the auth | refused | **Executed**: `(False, "bad directory authority")` |
| RT-03 | Open an account, pass a hostile `vaultUri`, capture the proof, replay it | refused; the hostile contract is never called | **Executed**: `(False, "no currency")`, hostile vault not reached |
| RT-04 | Pass a caller facet with a `withdraw`/callback arm; assert only `deposit` is called | no non-sink call | Covered by `G-CAP-AUTH` and the `depositFacet` construction; no runtime test yet |
| RT-05 | Use account A's proof/account bundle on B's vault, wrong deployerId | refused | The suite creates per-owner accounts; `RT-13` exercises the vault auth gate. A cross-owner replay term is the next addition |
| RT-06 | Replay admin/market/feed/currency signatures; cross-domain substitution | refused; canonical encoding | Open (OCAP-09); the gate counts the preimages |
| RT-07 | Publish/resolve a bundle, cross a block boundary, call it; introspect | persists; cannot destructure | Empirical, by `install_testnet.py`'s signed reads after every step |
| RT-08 | Pause/delist a vault/market/issuer, then use it | refused | Market pause/delist is exercised by `unit_market`; currency pause by `unit_stablecoin` |
| RT-09 | Substitute a caller URI for a pinned component | refused | **Executed** as RT-03; the pinned URI is the registry's `vaultUri` |
| RT-10 | Wrong secret, foreign refund, claim/refund race, opId replay | refused/terminal | Exercised by `unit_transfer` |
| RT-11 | `Root.resolve` after `deprecate`; `TradabilityGate` with `active` | deprecate refuses; active admits | **Executed**: active `(True, uri, version)`, unknown `(False, "unknown component")`, stale `(False, "stale")`, gate `(True, Nil)` |
| RT-12 | Lock funding/activation front-run with a different funder/beneficiary | refused | Open (OCAP-12); `unit_market` exercises the positive lock path |
| RT-13 | Rotate a vault auth, then use the old auth | rotated-out auth refused | **Executed** below |

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

- The negative issuer-arm tests (RT-01) and the cross-owner replay (RT-05) need
  a stablecoin system and are not automated yet; the capability gate covers the
  same boundary lexically.
- Signed-payload replay (RT-06) is open until the canonical Codec replaces the
  `toString()`/`"|"` preimages (OCAP-09).
- The lock front-run (RT-12) is open (OCAP-12).
- A fresh install is the gate for the dispatch fixes; a stale install is not
  evidence. The results above are from a fresh install.
