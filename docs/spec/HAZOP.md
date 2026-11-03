# HAZOP — shared channels, concurrency and node utilization

This is the channel classification and guide-word record referenced by
[`book/src/trust/verification.md`](../../book/src/trust/verification.md). It covers the
R-Cash Rholang suite (`contracts/src/deploy/v3/`), the Rust client
(`crates/rcash-chain`, `crates/rcash-sdk`, `crates/rcash-cli`) and the hostlist write path.
It is a design review, not a proof and not an audit. The review date is 2026-11-03 on
`docs/mdbook-rewrite`.

## 1. Merge model

rholo is not Ethereum. Its merge rule is **one pre→post diff per channel and a whole-deploy
rejection on conflict**. Two separate deploys cannot interleave on one state cell; the loser
is rejected entire. The reachable races are therefore *intra-deploy* (one term invoking the
same arm twice concurrently) and non-atomic multi-cell compositions. The linear-cell
discipline is specified in [`00-CALCULUS.md`](00-CALCULUS.md).

## 2. Channel classification

| Channel | Scope | Access | Conflict rule | Hazards found |
|---|---|---|---|---|
| `rootState` | global | peeks for resolve; take on bootstrap/admin writes | whole-deploy rejection on concurrent writes | writes are bootstrap/admin only; no hot path |
| `governorState` | global | take after `AdminGuard.verify`; per-domain nonce | nonce monotonicity rechecked after take | admin operations only; nonce ordering can lose an authorized action (liveness) |
| `currencyState` | global | take at commit; peeks for reads | one writer; `pausedRev` CAS mirror | pause/mirror divergence (fixed with `pausedRev` CAS) |
| `stablecoinDirectoryState` | global | take at commit | single writer (`directoryAuth`) | listing only |
| `oracleRegState` | global | take at commit | single writer | registration only |
| `termsState` | global | take on `put`; peeks for reads | content-addressed, idempotent | unauthenticated `put` can grow state (open) |
| `directoryState` | global | take on bind/seal | create-only bind; sealed slots immutable | partial commit before stage (fixed) |
| `indexState` | global | take on stage/activate/status; peeks for reads | one writer; pair ownership checked at activation | two drafts could both activate (fixed) |
| `feedState` | per currency | take after signature/freshness | one feed per currency | three reporters; short critical section |
| `issuerState` | per currency | take across native mint/burn | optimistic `totalPrincipal` compare | serial per currency; conflicts fail `1/0` |
| `paramsState` | per currency | peeks; take on apply | governor timelock | parameter changes are rare |
| `vaultState` | per currency | peek, work, take, revalidate `rev` | optimistic; whole-deploy rejection | serial per currency; conflicts fail `1/0` |
| `savingsState` | per currency | take across native deposit/withdraw | single writer; `rev` now incremented | serial per currency; zero-share notify race (fixed) |
| `bufferState` | per currency | peek/take; `paySavings` revalidates `rev` | single writer | serial per currency; `paySavings` no longer holds it across notify |
| `psmState` | per currency | peek, value movement, take, revalidate `rev` | optimistic | serial per currency; post-effect conflicts fail `1/0` |
| `poolState` | per market | peek, external reads, take, revalidate `rev` | single writer; `rev` now incremented | hold-across-call (fixed with P3); per-market commit is inherently serial |
| `lockState` | per market | take after Clock/identity reads | single writer | one-shot; no hold across Clock |
| `accountState` | per owner | take/repost before and after sends | per-owner short critical section | excellent |
| `purseState` | per owner | peek; native purse outside the take | per-owner | excellent |
| `transferState` | per transfer | peek, deposit, take/revalidate, terminal post | per-transfer consume | claim/refund terminal-on-failure (fixed); caller facet no longer held |
| `factoryState` | global | take only for a new owner | short critical section | account creation only |
| `bookParamsState` | global | peek | immutable after init | no shared send cell |

**Execution ceiling.** The suite is well-sharded by domain: per owner, per transfer, per
market, per currency. Cross-market and cross-currency operations run in parallel. A single
hot pair is serialized by `poolState`; a single currency's vault/savings/PSM operations are
serialized by their joint invariants (S2/S3/S10). That ceiling is a property of cell
granularity, not of the hold time: the FxPool P3 refactor lowers phlo and the lost-cell
window but does not multiply commits per block.

## 3. Findings and dispositions

| ID | Finding | Disposition |
|---|---|---|
| HAZ-01 | `createMarket` committed bind+seal before the stage guard; a stage refusal left a sealed slot for an unstaged market; a duplicate could overwrite a draft slot | Fixed: `MarketIndex.checkStage` pre-check before any write; create-only/idempotent `bind`; `fail()` after directory writes; sponsor `deployerId` required |
| A1 | Claim/refund marked the transfer terminal on any facet reply; a refused deposit stranded the payment | Fixed: P3 (`peek → verify → deposit → take/revalidate → terminal`), `fail()` on a facet refusal |
| A2 | Native-deposit catch-all branches returned a payment name after it may have been consumed | Fixed: post-native refusals call `1/0` |
| A3 | `poolState.rev` was dead; savings deposit/withdraw did not increment `rev` | Fixed: every successful pool/savings mutation increments `rev` |
| A4 | `byPair` was set at stage and never checked at activation; two drafts could activate | Fixed: activation pair guard; both orientations written in the same `indexState` commit; `draft → delisted` abandon edge |
| HAZ-02 | FxPool held `poolState` across every external read and the native effect | Fixed: P3 for swap/add/remove; `rev` revalidation; pre-effect `conflict` refusal |
| HAZ-03 | Write routing used only the cheapest fee tier; the pool was truncated before probing; non-proposers were dropped | Fixed: `Balanced` default, configurable fee band, wave verification, configurable pool size |
| HAZ-04 | Anchor at the minimum tip could leave one block of deploy lifespan | Fixed: tip-skew window and anchor near the chosen node's tip |
| HAZ-05 | A live `acceptsDeploys=false` node could be selected and signed for | Fixed: live status skip before signing |
| HAZ-06 | `setPaused` was a non-atomic two-cell update | Fixed: `pausedRev` CAS in `VaultBook.pause` and the registry mirror |
| HAZ-07 | `paySavings` could notify a zero-share pool | Fixed: `notify` refuses `"no shares"`; `paySavings` is P3 and returns the interest to the buffer |
| HAZ-08 | Optimistic `rev` conflicts surfaced as opaque `1/0` failures | Partially fixed: pre-effect `conflict` refusal; pre-acceptance retry policy remains a client follow-up |
| HAZ-09 | `LiquidityLock.fund` returned the original LP payment from a catch-all failure branch | Fixed: post-native refusal calls `1/0` |
| HAZ-10 | `bindings` grew without bound; a cancelled refresh could wedge discovery | Fixed: bounded pin map; `RefreshGuard` clears the single-flight flag on every exit |
| HAZ-11 | Sequential candidate probes; cold start could plan from the seed only | Fixed: bounded parallel probes; bounded join of an in-flight refresh |
| HAZ-12 | No load/soak test or utilization metrics | Partial: per-endpoint counters and `doctor --json`; a load harness is still to run |
| HAZ-24 | CLI `v4 send` defaulted to an empty opId, disabling the on-chain ledger | Fixed: generated and printed opId; retry reuses it |
| A5 | One issuer/vault/savings/PSM cell per currency caps contract-level concurrency | Documented; a per-vault shard plus totals is a separate design spike |
| A6 | `MarketTerms.put` stores unauthenticated content-addressed terms before the sponsor check | Open; griefing cost only |
| A7 | Sponsor signature has no deployment domain, nonce or deadline | Open; the `deployerId` check removes third-party relay |
| A11 | Hostlist accepts private addresses and future `generatedAt` | Partial: future-skew rejection; private-range policy open |
| A12 | Every typed write blocks on finality; no pipeline | Fixed in the SDK: `deploy_terms`/`submit_terms`; POST timeout remains open |

## 4. Verification

- `make spec-check`, `make formal-check`, `make pre-devnet-check` are the static gates.
- Rust tests cover fee-band selection, tip windows, closed-node skipping, batch deployment
  and anchor bounds (`crates/rcash-chain/src/node/pool.rs`, `node/mod.rs`,
  `crates/rcash-sdk/tests/hostlist.rs`).
- Contract flow YAML, Lean names and the acceptance map are updated with the arms above.
- The behavioural harness scenarios for concurrent market creation, transfer facet
  refusal, pause interleaving and savings notify are the next evidence step on a live
  devnet; a green static gate is not a conformance campaign.
