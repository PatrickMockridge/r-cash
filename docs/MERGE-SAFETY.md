# Merge safety: contract HAZOP, hardening and test record

Status: v0.5 hardening, 2026-10-24. This document is the HAZOP and the evidence map for
r-cash on the **fixed** rholo node. It is not a safety proof.

## 1. Scope and the node behaviour we are working against

The application is unchanged in intent: non-custodial purses, claimable transfers, signed
markets and REV-collateralised stablecoins. The node underneath it now:

- applies a merge as **one pre→post diff per channel** (C336, #434). The deployed rhobot
  chain predates this fix and is not a test target;
- resolves divergent writes by a deterministic lexicographic-minimum set of **whole
  deploys**; the losers are recorded in the block's `rejectedDeploys` and the deploy's own
  status may still read `ProcessedWithSuccess`;
- refuses work under pressure before decoding: HTTP `503` + `Retry-After: 1`, per-peer
  `429`, gRPC `RESOURCE_EXHAUSTED`, `acceptsDeploys:false` in `/api/v1/status`;
- refuses a byte-identical resubmission before parsing while the deploy is pooled;
- caps the pool at 64 MiB of term bytes and 1,000 deploys per deployer;
- anchors a deploy for about 50 blocks from `validAfterBlockNumber`;
- publishes `CURRENT_ROOT` only for an accepted block (law 80).

The contract-level consequences are the whole of this document:

1. **Two writers on one linear channel from divergent branches conflict.** One deploy is
   rejected wholesale; its value effects do not survive. This is safe but a liveness cost,
   and the client must detect it and retry under a new operation id.
2. **Writers on distinct channels both survive.** Per-owner and per-transfer cells are the
   design's concurrency boundary.
3. **A deploy status is not inclusion.** The merge block's `rejectedDeploys` and the
   postcondition read at a finalized block are the evidence.
4. **A merge's own pre-state is the merged state of its parents**, not either parent's
   post-state.

## 2. Method and classification

Every `new` name that can carry a message is classified:

| Class | Meaning in this codebase |
|---|---|
| **L** linear state cell | one message, consumed and re-posted; the cell is the serialization point |
| **A** append-only / insert-only | a key is added once and never removed (`Root.register`, registry maps) |
| **P** per-instance | one cell per owner or per transfer; distinct channels by construction |
| **N** mergeable number | the node joins the diffs; **no r-cash state relies on this** |
| **R** request/response | one-shot channel; no cross-block state |

The only cross-block read-modify-write that remains on a path with more than one possible
writer is the serialization domain itself (pool, vault, factory, feed, registries). Its
conflict rule is stated in §4. The transfer-id counter and the Root install burst were
removed or serialized.

## 3. Shared-channel inventory

Line references are `contracts/src/deploy/v3/…`; `contracts/build/deploy/v3` is generated
from these by `tools/build_contracts.py`.

| Cell | File:line (seed / main write) | Class | Writers | Cross-block RMW | Merge / replay / pressure / restart |
|---|---|---|---|---|---|
| `rootState` | `00_root.rho:256`, register `:57-83` | A on an L cell | installer (`register`); governors (`rotate/deprecate/freeze/admin`, first read is a peek `<<-` at `:87/:136/:170/:197`, second read consumes and reposts) | `register` consumes/reposts; governance consumes once after authorization | Divergent `register`/admin writes conflict → one deploy rejected wholesale; installer serializes. Replay: `govNonce` + duplicate-key refusal. Pressure: 503 before parse, retry same bytes. Restart: the accepted block's post-state is canonical. |
| `governorState` | `04_governor.rho:159`, `authorize :34-56` | L | any component calling `authorize`, one nonce per domain | consume/repost after `AdminGuard.verify` | Divergent authorize calls conflict; one deploy rejected. Replay: `nonces` map. |
| `factoryState` | `09_identity.rho:400`, `getOrCreate :18-365` | L | any owner calling `getOrCreate` | double-checked peek → consume → repost `:22-27,343` | One account per owner; divergent creations for different owners conflict, one account orphaned (no value at creation); retry `getOrCreate`. |
| `purseState` | `09_identity.rho:187` | P (one per owner) | the owner's account arms | `ensure` peek → consume → repost `:44-88` | Single writer: no cross-owner conflict. Same owner's concurrent writes conflict; one deploy rejected. |
| `accountState` (**new**) | `09_identity.rho:188`, `sendTransfer :256-…` | P (one per owner) | the owner's `sendTransfer` | consume → increment → repost **before any await** at `:267-274` | Single writer. Two sends by one owner on divergent branches conflict; one deploy rejected; the id is display-only (the transfer URI is the handle). |
| `bookState` (**removed**) | was `40_transfer.rho:43,148` | — | — | removed in v0.5 | The send path has no shared counter; the caller supplies `@id`. |
| `transferState` | one per transfer, `40_transfer.rho` claim/refund/info | P (one per transfer) | claim or refund, once | consume → terminal status reposted | **Intended exclusivity**: claim and refund conflict; exactly one wins, the other deploy is rejected wholesale. No partial deposit survives. |
| `issuerState` | `31_stablecoin.rho:1017`, `mint :312`, `burn :346` | L | only the VaultBook holds `mintAuth`/`burnAuth` | peek → consume → effect → repost; **every branch reposts**, including `"changed"` `:323,:362` | One issuer per currency; a divergent mint/burn conflict rejects one deploy. Supply and principal move together. |
| `vaultState` | `31_stablecoin.rho:1021`, `VaultBook` arms | L | any vault owner / liquidator | peek → validate → value effect → consume/recheck/commit (mint, withdraw, liquidation) | Serialization domain: divergent writes conflict, one deploy rejected wholesale. Invariants S1–S7 hold for the accepted branch. |
| `stablecoinDirectoryState` | `32_currency_registry.rho:218` | A on an L cell | only `CurrencyRegistry` (it holds `directoryAuth`) | `register :19-31` consumes/reposts | One system per code; duplicate refused. Divergent listings conflict. |
| `currencyState` | `32_currency_registry.rho:219`, `register :71-138` | A on an L cell | sponsor-signed registrations; governor pause | directory write then currency consume/repost | Duplicate code refused; a race `1/0` reverts the deploy (including the directory write). |
| `oracleRegState` | `12_oracle_registry.rho:282`, `regBind :143`, `admin :227` | A on an L cell | sponsor-signed feed bind; governor admin | consume/repost | Duplicate feed/reporter refused; one deploy wins a conflict. |
| `feedState` | `31_feed.rho:376`, `submit :166-232` | L | the three reporters; governor | peek → verify → re-read → consume/repost with `rev` check | Five value-free observations; a divergent submit conflict rejects one deploy (liveness only). Replay: height-monotonic + `seenN`. |
| `termsState` | `50_market.rho:587`, `put :66-91` | A on an L cell | anyone paying phlo | consume/repost; content-addressed, insert-only | Same terms re-put is idempotent (returns the existing hash). |
| `directoryState` | `50_market.rho:588`, `bind/seal :116-147` | L | only `MarketFactory` holds `marketAuth` | consume/repost | One slot per market; seal is terminal; divergent factory calls conflict. |
| `indexState` | `50_market.rho:589`, `stage/activate/setStatus` | L | factory, governor | consume/repost | Pair uniqueness and version monotonicity in one cell; conflict rejects one deploy. |
| `termsState` / `indexState` / `directoryState` | as above | L | MarketFactory sequence | three cells in one deploy | A failed factory reverts; a conflicting factory deploy is rejected wholesale. No compensation is needed because the whole deploy is the unit. |
| `poolState` | `51_pool.rho:420`, swap `:243`, add/remove `:340/:381` | L | any swapper/LP | peek/consume → ERTP effects → state commit; failures `1/0` | Serialization domain. Divergent swaps/liability writes conflict, one deploy rejected; no partial state in the accepted branch. |
| `lockState` | `51_pool.rho:543` | L | funder, beneficiary, governor | consume/repost for fund/release/cancel | **No linear payment is stored in the cell.** The LP payment sits in `lockPurse` (created in `assemblePool`); the cell holds flags, height, shares and addresses only. |
| `lockPurse` (**new**) | `51_pool.rho` (one per lock) | native ERTP purse | fund/release/cancel | native ERTP reply per arm | A merge that rejects the deploy drops the deposit/withdrawal with the whole deploy. |

## 4. Conflict rule for the serialization domains

`VaultBook`, `FxPool`, `AccountFactory`, `OracleFeed`, `CurrencyRegistry`, `OracleRegistry`,
`MarketIndex`, `MarketDirectory` and `MarketTerms` are **one linear cell each**. The rule,
stated once and tested by T1-B/T2-b:

> A write consumes the cell, validates and performs its value effect, then re-posts. Two
> divergent writes to the same cell conflict; the merge keeps one deploy and records the
> other in the block's `rejectedDeploys`. The rejected deploy is dropped **whole**: its ERTP
> deposits, withdrawals, mints and burns are not half-applied. The client must read the
> block's `rejectedDeploys` and the postcondition at a finalized block; a rejected operation
> is retried under a **new** operation id with a fresh signature.

The safe patterns used where the work can be partitioned:

- **insert-only register** — `Root.register` (key = operation), currency/feed/terms maps;
- **per-writer cell** — `purseState` and `accountState` (one owner), `transferState` (one
  transfer), `lockState` (one lock);
- **distinct channel per instance** — `TransferContract` per transfer and `FxPool` per
  market; two different instances never share a state channel.

No r-cash logic relies on a mergeable-number join. The former `bookState` counter was the
only candidate and is gone.

## 5. Root registers and the install sequence

`Root` is the only singleton directory. Every component self-registers during its own
deploy; the installer treats each deploy as a **dependent step** and verifies it before
building the next term.

| Step | Deploy | Registers | Depends on | Verification before the next step |
|---|---|---|---|---|
| 00 | `00_root` | `rcash:root` | — | `Root.resolve("rcash:root")` at the carrying block |
| 03 | `03_admin_guard` | `component:admin-guard` | Root | resolve |
| 01 | `01_kernel` | `component:clock`, `component:verifier`, `component:codec` | Root | resolve all three |
| 02 | `02_bounds` | `component:bounds` | Root | resolve |
| 04 | `04_governor` | `component:governor` | Root | resolve |
| 05–08 | math and claim code | `component:amm-math`, `collateral-math`, `oracle-math`, `claim-code` | Root | resolve each |
| 12 | `12_oracle_registry` | `component:oracle-registry` | Root | resolve |
| 13 | `13_oracle_hub` | `component:oracle-hub` | Root | resolve |
| 32 | `32_currency_registry` | `component:stablecoin-directory`, `component:currency-registry` | Root | resolve both |
| 14 | `14_asset_resolver` | `component:asset-resolver` | Root | resolve |
| 40 | `40_transfer` | `component:transfer-book` | Root | resolve |
| 51 | `51_pool` | `component:pool-template` | Root, AssetResolver URI | resolve |
| 50 | `50_market` | six `component:market-*` / view keys | Root, AssetResolver URI | resolve all six |
| 09 | `09_identity` | `component:account-factory` | Root, AssetResolver URI | resolve |

Per currency and market, later steps are separate deploys (`31_feed` → registry bind,
`31_stablecoin` → currency register, `MarketFactory.createMarket`). They are listed in
`docs/spec/30-WIRING.md`; each returns a value the caller can verify.

The "resolve" in the last column is a **signed read at the current finalized state**, not
`explore-deploy-by-block-hash`: on this node the explore endpoint cannot see the native
registry (§8.2.1). The carrying block is still required to be finalized, so its post-state
is canonical; the read is made after that check.

`Root.register` duplicate rule: insert-only, existing key wins, `(false, "duplicate")` for a
re-register, `(false, "frozen"|"not installer"|"bad version")` otherwise. A byte-identical
resubmission is refused by the node before parse while pooled; after inclusion the same
bytes are a `Replay` and must not be treated as a new operation. The installer's operation
cache is keyed by step, so a retry reuses the signed bytes.

## 6. Refusal taxonomy and the client contract

| Outcome | HTTP | Meaning | Client action |
|---|---|---|---|
| `RateLimited` | 429 | per-peer limit | retry after `Retry-After`, bounded backoff + jitter |
| `Unavailable` | 503 | memory gate / admission / in-flight capacity, refused before decode | retry after `Retry-After`; preflight `acceptsDeploys` and stop if false |
| `AdmissionRefused` | 4xx | a floor/config refusal | report `REFUSED`; do not retry the same bytes |
| `Duplicate` | 4xx/body | byte-identical deploy is known | treat as submitted; poll status; never assume a new effect |
| `TermTooLarge` | 4xx | > 64 KiB parse bound | fail the step; the installer budget is 48 KiB |
| `ProcessedWithSuccess` | — | executed in a block | check the block is finalized and not in `rejectedDeploys`, then read the postcondition |
| `ProcessedWithError` | — | reverted and charged phlo | fail the step |
| `StillUnknown` | — | timeout | never retry a value-moving deploy blindly; use the cached signed bytes or prove the effect absent |

`harness/chainclient.py` implements this for the installers and the arms. The Rust client
(`crates/rcash-chain`) classifies the same outcomes, backs off with jitter, and carries the
signed-deploy cache (`deploy_term_cached`) used by `rcash deploy --op`.

## 7. What changed in v0.5

The "Test" column names the test that would catch a regression. The merge arms referenced
there were not reached on this host (§8.3); the Rust and harness unit tests and the install
pass did run.

| Finding | Change | Test |
|---|---|---|
| Global transfer-id counter (`bookState`) was a shared linear cell on every send | per-owner `accountState`; `TransferBook.send` takes `@id`; the counter is consumed and reposted before any await | unit transfer; T1-A/B |
| `issuerState` consumed without a repost on the `"changed"` branch | both branches repost | unit stablecoin race |
| Commit-before-effect in vault mint/withdraw/liquidation | value effect first, then a rechecked consume/commit | unit stablecoin; T1-B |
| A linear LP payment stored in `lockState` | `lockPurse` holds it; state holds flags/shares | unit market; restart arm |
| Install burst with unchecked acks | per-step inclusion + `Root.resolve` verification before the next step; `--allow-live` guard; chain-aware resume | T2, T3, T4 |
| No refusal classification or backoff | `ChainError` variants; `PollPolicy` backoff+jitter; `chainclient.py` | Rust unit tests; T4 |
| Installer trusted local state only | chain-aware complete/fresh/repair modes | T2 re-run |

## 8. Devnet evidence

Run of 2026-10-25 on a disposable devnet built from the fixed source:

| Fact | Value |
|---|---|
| Node source | `ee72656eacb03d6656664c8f2b9b912ad7ad9cb4` |
| Image | `rnode:local`, `sha256:25ee8040c00ce5caa61b16a2d8b46188235a2de1d042e2db1ee89ecf548d885c` |
| Topology | `DEVNET_PREFIX=rcash`, four validators, `DEVNET_NODE_MEMORY=2g`, `--no-autopropose`, epoch length 10 |
| Install target | `http://localhost:41403` (validator-1) |

### 8.1 Install (pass)

All 17 install steps completed. Each step was accepted, processed, its block finalized, and
every expected `Root` key resolved before the next dependent term was built. The rendered
terms were minified and measured at 0.5–14.5 KiB, well under the 64 KiB parse bound. The
manifest was written with no null fields. A second run found every key present at the
finalized state and skipped all 17 steps, then rewrote the manifest: the install is
chain-aware and re-runnable.

### 8.2 Platform observations (recorded, not r-cash findings)

1. **Exploratory deploys cannot see the native registry on this node.**
   `rho:registry:lookup` inside `POST /api/v1/explore-deploy-by-block-hash` returns `Nil` for
   a URI that a signed deploy resolves immediately. Root verification therefore uses a small
   signed read at the current finalized state; `harness/chainclient.py` and the installers
   document this. A pinned historical `Root` read is not available on `ee72656ea` with the
   explore endpoint.
2. **The devnet's partition/heal does not re-establish merge gossip.**
   The arms split bootstrap+validator-1 from validator-2+validator-3 with
   `docker network disconnect` (and a second bridge for the isolated pair). Each side can
   propose, but after reconnect the nodes do not exchange the divergent tips: heights stay
   apart and no multi-parent merge block appears. This is a property of the disposable
   devnet/peer-discovery topology, not of the r-cash contracts. It is an upstream
   rholo-devnet limitation and is not worked around here.

### 8.3 Arms

| Arm | Result | Reason / evidence |
|---|---|---|
| Install (17 steps) | **pass** | §8.1 |
| T1-A0 (upstream distinct-channel control) | **not reached** | devnet partition/heal observation §8.2.2 |
| T1-A (two owners, divergent sends) | **not reached** | same |
| T1-B (same owner, stated conflict rule) | **not reached** | same |
| T2-a (16 sequential registrations) | **not run** | requires the same partition harness for its second half |
| T2-b (divergent registrations) | **not reached** | same |
| T3 (restart read-back) | **not run** | depends on a merged anchor block from T1 |
| T4 (1 GiB pressure) | **out of scope** | the node now gates admission on resources; 1 GiB is not a production target and the operator selected it out |

No claim is made that the fork-point or restart acceptance criteria are met. The contract
changes above stand on their own reasoning and the install evidence; the merge arms are a
verification gap, not a green result. The public-testnet version of these arms is proposed
upstream in [rhovision-org/rholo#447](https://github.com/rhovision-org/rholo/issues/447).

## 9. Residual risks and non-claims

- An install pass is **not** a safety proof. It exercises one node build and one linear
  chain; the merge arms did not run (§8.3).
- The partition/heal and merge arms remain unverified on this host because the disposable
  devnet does not re-establish merge gossip after reconnect. That is an upstream
  rholo-devnet limitation, not a finding about the r-cash contracts, and no contract
  conclusion is drawn from it.
- The live rhobot chain predates C336 and cannot be repaired by these changes. No live
  deploy was performed for this record.
- Merge semantics and the Rholang runtime are the node's (laws 72/80, C336). This document
  does not redefine them, and no node, genesis or consensus file is changed.
- Multi-writer serialization domains can still lose one operation to a merge rejection.
  That is safe (whole-deploy rejection, no partial value movement) but is a liveness cost;
  the client retries under a new operation id after proving the old effect absent.
- A native ERTP reply that never arrives can still strand a cell between consume and repost.
  The code follows the platform rule that hot-path native channels reply exactly once; this
  is not proved here.
- The browser client does not yet carry a signed-deploy cache; a user-triggered retry of a
  value-moving WASM operation relies on the operator's UI discipline. The CLI and the
  installers do.
- Tests run against `ee72656ea`. A later node tip must be re-run, not assumed.
