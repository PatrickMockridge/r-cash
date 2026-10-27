# R-Cash multi-stakeholder review

Date: 2026-10-27. Baseline commit: `d95da95` (`main`). Scope: the v0.4 Rholang contracts
and the Rust/TypeScript app. This is a static, read-only review at that commit; it is not a
security proof, an economic audit, or a mainnet-readiness statement. The remediation column
is a plan, and this document is updated as fixes land.

## 1. Verdicts

| Stakeholder | Verdict | Headline |
|---|---|---|
| **Payment senders** | **Usable, not safe to retry or trust at finality** | The send is one deploy with no protocol fee, but a timeout retry can double-escrow, the UI reports success before finality, and the web has no refund/history path. |
| **Payment receivers** | **The claim link works; onboarding does not** | Funds can only go to the recipient facet bound at send, but the receiver must already hold REV to pay phlo, and a direct caller can advertise an amount/asset it did not escrow. |
| **Collateral suppliers / stablecoin holders** | **Collateral works; there is no yield and no redemption** | Vaults mint and liquidate, but interest is burned with no recipient, stablecoins are not redeemable at par, and no client exposes vault health or liquidation. |
| **Human market makers** | **Cannot operate as a market maker** | There is no createMarket, no RFQ/limit orders, no maker rebate, no per-market control, and the governor's pause/delist does not stop the pool. |
| **AMM LPs** | **There is a real fee stream, but the lifecycle has a fund-losing path and a pool-bricking exit** | Spread accrues to LPs, but add-and-lock on a funded lock can strand the LP payment, and removing all liquidity permanently prevents re-seeding. |

The economic model is DAI-shaped but incomplete: the stability fee has no `vow`, there is no
savings rate (`pot`/DSR), and there is no PSM/redemption facility. AMMs exist, so the
secondary peg has a venue; the protocol-level floor and the surplus/bad-debt loop do not.

## 2. Method and evidence standard

- Three read-only explorations covered the payment, stablecoin/collateral and market/AMM
  paths across contracts, SDK, CLI, wasm, web, docs and harness.
- The highest-impact claims were re-read directly in the contracts and clients.
- Status labels: **Confirmed-static** (the code path is traced and the consequence follows),
  **Confirmed-test** (an existing test exercises it), **Reproduced-devnet** (run on the
  disposable fixed-node devnet), **Unverified** (plausible, not traced to the end),
  **Product** (a missing capability or economic design, not a code defect).
- Severity: **Critical** = direct loss/permanent lock in the intended flow or a completely
  inert safety control; **High** = material loss/denial/invariant break or a core promised
  behaviour absent; **Medium** = bounded defect or privileged path; **Low** = docs/UX/minor.
- Evidence is what the code does; inference is the consequence and has a precondition and a
  falsifier. No exploit is claimed from a design gap.
- No public-testnet mutation. The 1 GiB case is out of scope: the node now gates admission
  on resources.

## 3. Authority and asset flow

| Role | Capability | Where |
|---|---|---|
| Owner | account arms, purses, send/claim/refund, vault auth token | `09_identity.rho:18-365`, `31_stablecoin.rho:461-508` |
| Installer | `Root.register` (insert-only) | `00_root.rho:57-83` |
| Governor (2-of-3) | market status, vault pause, registry pause, lock cancel, registry/parameter domains | `04_governor.rho:159-163`; callers in `50_market.rho:330-364`, `31_stablecoin.rho:972-993`, `32_currency_registry.rho:186-216`, `51_pool.rho:497-528` |
| Sponsor | signs market terms and feed policy | `50_market.rho:467-585`, `31_feed.rho:166-232` |
| Reporter (3) | signed price submissions | `31_feed.rho:166-232` |
| Liquidator | permissionless, holds stablecoin + phlo | `31_stablecoin.rho:824-914` |
| Anyone | activate a seeded market, claim with secret, swap/LP against a public pool URI | `50_market.rho:255-305`, `40_transfer.rho:45-81`, `51_pool.rho:234-418` |

Value path: owner purse → withdraw on send → `TransferContract` closure (escrow) → recipient
deposit facet on claim, or sender refund facet on refund. Stablecoin path: REV custody →
vault debt → stablecoin mint → repay/burn, or liquidation burn + REV seizure. FX path:
account withdraw → pool deposit/output withdraw → account deposit.

## 4. Lens 1 — payment senders

### Journey

1. Web `/pay`: recipient public key, asset, amount, expiry in blocks. A 32-byte claim secret
   is generated in the browser and hashed with BLAKE2b-256 (`Pay.tsx:29-36`,
   `rcash-chain/src/claim.rs:24-33`).
2. Expiry becomes `tip.height + blocks` (`Pay.tsx:51-53`), then one signed deploy creates the
   sender and recipient accounts, obtains the recipient deposit facet, withdraws the amount,
   and calls `TransferBook.send` (`v4.rs:390-429`, `09_identity.rho:259-318`).
3. The sender copies `#/claim/<transfer-uri>/<secret>` (`Pay.tsx:64-65`).

There is no protocol transfer fee. The sender pays phlo for the deploy, including creating
the recipient account and purse. There is no FX conversion in `send`; cross-currency is a
separate `Convert`/pool swap.

### Findings

- **PAY-02 (High, Confirmed-static): writes report success at inclusion, not finality.**
  `deploy_term` waits for finality and records `finalized` (`lib.rs:177-195`), but
  `signed_value` returns `ProcessedWithSuccess` without consulting it (`lib.rs:361-382`).
  Expiry and lock heights also use `latestBlockNumber`, not a finalized height
  (`lib.rs:335-338`, `node/mod.rs:198-204`, `Pay.tsx:51-53`).
- **PAY-03 (High, Confirmed-static): no idempotency for v4 sends.** The cached-deploy path
  exists only for `deploy --op` (`lib.rs:208`); `v4_tx` uses plain `signed_value`
  (`v4.rs:164-168`). A timeout followed by a retry allocates a new per-owner id
  (`09_identity.rho:266-274`) and creates a second escrow.
- **PAY-04 (High, Confirmed-static): transfer bounds are not enforced.** `send` checks only
  `amount > 0` and `expiry > now` (`40_transfer.rho:35-43`); `Bounds.checkBook`
  (`02_bounds.rho:63-74`) has no production caller. Dust and arbitrarily long expiries are
  possible. `20-INVARIANTS.md:105-109` says the opposite.
- **PAY-05 (High, Confirmed-static): claim has no expiry gate.** Claim checks status and
  secret only (`40_transfer.rho:45-81`); refund checks expiry (`:97`). After expiry both
  race on the same cell. A sender cannot rely on expiry to stop a claim.
- **PAY-07 (Medium, Confirmed-static): zero slippage defaults.** Convert initialises
  `minOut=0` (`Convert.tsx:19`); LP add/remove pass zero minima (`v4.rs:511,547`).
- **PAY-09 (High, Confirmed-static): web has no refund action or history.** `Pay.tsx:78-80`
  promises refunds, but no web code calls `v4_refund_transfer`; the transfer URI is only in
  component state, and the IndexedDB journal is not used by Pay.
- **PAY-06 (Medium, Product): no memo/reference and public, reused sender address.** `info`
  exposes sender, asset, amount, expiry and status (`40_transfer.rho:132-143`); one account
  per key (`09_identity.rho:390-404`) makes every send linkable to one pseudonym.
- **PAY-08 (High, Confirmed-static): send trusts the caller's declared amount/asset.** A
  direct caller can pass `amount=100` with a 1-unit payment, or mislabel the asset; `send`
  never calls `getAmountOf` and never checks the brand (`40_transfer.rho:35-43`). The usual
  SDK path is safe because it constructs the facet and amount together
  (`v4.rs:403-416`), but a claim link is not self-verifying. The recipient facet is captured
  at send, so a claim cannot redirect funds.

## 5. Lens 2 — payment receivers

### Journey

Open the claim link, read the transfer record for free (`40_transfer.rho:132-143`), then
sign one deploy that calls `account.claimTransfer` → `TransferContract.claim`, which checks
the secret hash and deposits the escrowed payment into the recipient facet bound at send
(`40_transfer.rho:45-81`). The receiver pays phlo for this deploy.

### Findings

- **PAY-01 (High, Confirmed-static): a new receiver must already hold REV.** Claim is a
  signed deploy (`Claim.tsx:53-69`), and `Accounts.tsx:22-35,110-115` explicitly says every
  signed read/write costs phlo; the claim page has no funding step. The sender creates the
  receiver's account, but not its REV balance. A funded third party holding the secret can
  execute the claim and the funds still go to the captured facet, but no UI exposes this.
- **PAY-05** (above) means a receiver can lose a claim to a sender refund after expiry, or
  win after the sender expected to refund; the UI only checks status (`Claim.tsx:71,111-117`).
- **PAY-08** means a receiver cannot verify from public `info` that the advertised amount and
  asset were actually escrowed; a fake-payment link is possible outside the standard SDK.
- **PAY-06**: there is no reference/memo for reconciliation, and the receiver's on-chain
  identity is hidden by the facet indirection only until they claim.
- **STB-04 (High, client gap):** the claim is sound, but there is no notification, receipt
  or "pending" state; a timeout is a raw error string.

## 6. Lens 3 — collateral suppliers and stablecoin holders (yield)

### Journey (vault owner)

`VaultBook.open` creates a per-owner vault and returns a bearer auth token
(`31_stablecoin.rho:461-508`). The owner deposits REV into `CollateralCustody`, mints the
stablecoin against health `collateral·rate/1e8 · 10000 ≥ debt·mcrBps`
(`06_collateral_math.rho:27-37`, `31_stablecoin.rho:572-668`), accrues interest per block
(`06_collateral_math.rho:15-24`), repays, withdraws, or is liquidated at
`payout = amount·(10000+bonus)·1e8/(rate·10000)` (`06_collateral_math.rho:41-48`,
`31_stablecoin.rho:824-914`).

### Findings

- **STB-01 (High, Confirmed-static): repay drops accrued interest from the totals.**
  `VaultBook.repay` sets vault debt to `accrued − amount` (`31_stablecoin.rho:769,786`) but
  writes `totalDebt − amount` and leaves `totalAccruedInterest` unchanged (`:788-789`).
  Deposit, mint and withdraw correctly add `(accrued − v2.debt)` to both
  (`:543-544,627-628,713-714`). This breaks S2 (`20-INVARIANTS.md:39`) whenever repayment
  happens in a later block, and understates `totalDebt` for the ceiling check (`:603-605`).
- **STB-02 (High, Product): there is no yield path and no redemption.** Interest is burned
  on repayment (`31_stablecoin.rho:346-388,765`); `totalAccruedInterest` is a running total
  read only by `totals` (`:955-966`); REV in custody earns nothing; stablecoin holders have
  no redemption, only a secondary-market sale or repaying their own vault. The docs are
  honest about this (`STATUS.md:31-34`, `INTENT.md:43,98`), but the stakeholder named in this
  review has no product.
- **STB-03 (Medium, Confirmed-static): pause semantics are inconsistent.** The registry
  `setPaused` writes a status string (`32_currency_registry.rho:186-216`) that no issuer arm
  reads. `VaultBook.pause` is real but only `mint` checks it (`31_stablecoin.rho:576,618`);
  withdraw, repay, deposit and liquidation continue. A risk manager's "pause" does not stop
  collateral flight or a forced liquidation.
- **STB-05 (Medium, Product): bad debt is permanent.** Underwater clears book `badDebt`
  (`31_stablecoin.rho:213-236`) with no stability pool, treasury or surplus absorber. The
  shortfall is implicit in reduced backing and never crystallises without redemption.
- **STB-06 (Medium, Product): risk parameters are immutable.** MCR, bonus, close factor,
  rate, ceiling, min/max debt and oracle age are sealed at deploy
  (`31_stablecoin.rho:448-459`); governance can only pause mint. A volatility regime change
  needs a new system.
- **STB-04 (High, client gap): no vault/health/totals/liquidation surface.** The on-chain
  views (`31_stablecoin.rho:916-970`) are not in the SDK, CLI, wasm or web; the `vault` view
  itself computes health from stored, unaccrued debt (`:928-929`). A vault owner cannot see
  liquidation risk; a keeper has no tooling.
- **Liquidation:** permissionless and capital-light (stablecoin + phlo), first-come-first
  served, no keeper bond or auction; `minCollateral` is the liquidator's slippage guard.
  No client exposes it.

## 7. Lens 4 — human market makers

### Journey

A market maker constructs the 25-field terms, signs
`rcash:market-create:v1|marketId|termsHash|sponsor`, and calls
`MarketFactory.createMarket` (`50_market.rho:467-585`). The factory verifies the sponsor,
both live feed policies, creates the pool and lock, binds/seals the directory, and stages
the index. The sponsor (or anyone) seeds with `addLiquidity`, funds the one-shot lock, and
anyone activates once `lock.untilHeight >= terms.lockUntilHeight` and
`rq >= depthFloorQuote` (`50_market.rho:255-305`).

### Findings

- **MKT-01 (Critical, Confirmed-static): pause/delist does not stop the pool.**
  `setStatus` only rewrites the index record (`50_market.rho:330-364`). `FxPool.swap` and
  `addLiquidity` check `poolState.paused` (`51_pool.rho:242,338`), but that field is
  initialised false (`:421`) and has no setter anywhere. `quote` and `removeLiquidity` never
  check status either. A public pool URI keeps trading after the governor "pauses" or
  "delists" the market. `TradabilityGate` (`50_market.rho:366-380`) exists but the pool never
  calls it.
- **MKT-05 (High, Confirmed-static): no legal status transitions.** `setStatus` accepts any
  string (`50_market.rho:348-351`); I4's state machine is documentation only.
- **MKT-07 (High, Confirmed-static): 10 terms fields are hashed but not enforced.** `slug`,
  `sponsorOwnerId`, `minLiquidity`, `seedBase`, `seedQuote`, `seedInitialShares`,
  `lockBeneficiaryPubKey`, `lockMinBlocks`, `bookDefaultExpiryBlocks`, `bookMaxExpiryBlocks`
  appear only in the bounds/key list (`02_bounds.rho:95-102`); the factory and activation
  do not read them. The sponsor's signed seed/lock intent is not binding.
- **MKT-08 (High, Confirmed-static): canonical drift.** On-chain terms are length-prefixed
  (`01_kernel.rho:26-40`); `tools/market_terms.py:17,24-25` and `rcash-core/src/market.rs`
  use a plain `|` join and the v1 30-field schema, not v4's 25 fields.
- **MKT-03 (High, Confirmed-static): lock cancel pays the executor.** `LiquidityLock.cancel`
  is governor-gated but returns the LP payment to the caller, not the funder or beneficiary
  (`51_pool.rho:497-528`); release correctly checks the beneficiary (`:473`).
- **MKT-04 (Critical-static, runtime confirmation planned): add-and-lock on a funded lock
  strands the LP.** `v4_add_liquidity` mints LP then calls `LiquidityLock.fund`
  (`v4.rs:540-556`); `fund` refuses `"funded"` without returning the payment
  (`51_pool.rho:425-447`), and the SDK returns the refusal after the LP was minted. The web
  does not disable the action when `lock.funded` (`Liquidity.tsx:210`).
- **MKT-09 (High, Confirmed-static): web quotes always fail.** wasm `v4_quote` uses
  `self.reader()` (keyless) (`rcash-wasm/src/lib.rs:442-456,684-693`); the SDK quote uses
  `signed_value` (`v4.rs:285-306`), which needs a key.
- **MKT-10 (Medium, Product/spec): the pool economics differ from the spec.** `maxTradeBps`
  is compared to total pool value, not the input reserve (`51_pool.rho:256-257,276` vs
  `SPEC.md:355`); `minLiquidity` is only `>= 0` in bounds (`02_bounds.rho:47`); the
  first-deposit `1e8` deduction is not minted to a burn purse (`05_amm_math.rho:66`);
  there are no maker rebates.
- **MKT-11 (High, client gap): no market-maker surface.** There is no SDK/wasm/web
  `createMarket`, no Markets route (`App.tsx:21-49`), no standalone LP add/remove (only seed
  add-and-lock and release), no APR/NAV/PnL/lock countdown; `V4Lock` drops beneficiary and
  funder even though `info` returns them (`v4.rs:63-71,313-325` vs `51_pool.rho:530-541`).

## 8. Lens 5 — AMM liquidity providers

### Mechanics

The pool is a fixed-price oracle-anchored market maker, not a constant-product curve:
`value = floor(rb·rate/1e8)+rq`, `weight = baseValue·10000/value`,
`fee = baseSpread + |weight−5000|·skew/5000`, output is the oracle value less the fee
(`05_amm_math.rho:12-61`). Fees stay in reserves and accrue pro-rata to shares. Adds are
valued at the oracle ratio; withdrawals are pro-rata reserves (`51_pool.rho:89-156,371-418`).

### Findings

- **MKT-02 (High, Confirmed-static): full removal bricks the pool.** `removeLiquidity`
  never resets `seeded` (`51_pool.rho:97-102,149,378-399`). After total removal,
  `totalShares=0, seeded=true`; a new add takes the `seeded` branch, `AmmMath.shares` returns
  0 (`05_amm_math.rho:68-72`), and the add is refused `"shares"` forever. The LP burn result
  is also bound but never matched (`:392-407`), and `shares <= totalShares` is unchecked.
- **MKT-04** (above) is a direct LP loss in the intended seed flow.
- **MKT-01** means LPs cannot rely on a governor pause or delist to stop flow.
- **MKT-10** fee/floor/first-deposit economics differ from the spec; the symmetric skew fee
  penalises a rebalancing trade the same as a deepening trade (`05_amm_math.rho:30-40`;
  `SPEC.md:357-358` says otherwise).
- **Adverse selection:** the pool prices at a lagging oracle (up to `maxPairAgeBlocks`);
  `maxTradeBps` bounds one trade but not repeated draining. There is no commit-reveal or
  private order flow.
- **Exit path:** regular LPs can remove without a lock; the seed LP is locked. `cancel` pays
  the executor (MKT-03). There is no APR/NAV/PnL/lock countdown in the app.

## 9. Finding register

Status: C = Confirmed-static, T = Confirmed-test, D = Reproduced-devnet, U = Unverified,
P = Product/economic gap. Severity: Cr, H, M, L.

| ID | Sev | Status | Lenses | Finding | Evidence |
|---|---|---|---|---|---|
| MKT-01 | Cr | C | sender, receiver, holder, MM, LP | Pause/delist does not halt pool trading; pool `paused` has no setter and no status read | `50_market.rho:330-364`; `51_pool.rho:242,338,421` |
| MKT-04 | Cr | C/U | MM, LP | Add-and-lock on a funded lock mints LP and strands it | `v4.rs:540-556`; `51_pool.rho:425-447`; `Liquidity.tsx:210` |
| STB-01 | H | C | borrower, holder | Repay drops accrued interest from `totalDebt`/TAI; breaks S2 | `31_stablecoin.rho:762-789` vs `:543-544,627-628,713-714` |
| STB-02 | H | P | holder, yield | No yield path, no redemption; interest burned | `31_stablecoin.rho:346-388,765`; `06_collateral_math.rho:15-24` |
| MKT-02 | H | C | LP, MM | Full removal bricks the pool; burn unchecked; `seeded` never reset | `51_pool.rho:97-102,378-399`; `05_amm_math.rho:68-72` |
| MKT-03 | H | C | MM, LP | Lock cancel pays the executor, not funder/beneficiary | `51_pool.rho:497-528` |
| PAY-03 | H | C | sender | No idempotency for v4 sends; retry double-escrows | `v4.rs:164-168,390-429`; `lib.rs:208` |
| PAY-08 | H | C | receiver, sender | Send trusts declared amount/asset; fake-payment links possible | `40_transfer.rho:35-43` |
| PAY-05 | H | C | sender, receiver | Claim has no expiry gate; claim/refund race | `40_transfer.rho:45-81,97` |
| PAY-01 | H | C | receiver | Receiver needs REV for phlo to claim | `Claim.tsx:53-69`; `Accounts.tsx:22-35` |
| PAY-02 | H | C | sender, receiver | Writes report success before finality; expiry anchors to non-final tip | `lib.rs:177-195,335-338,361-382` |
| PAY-04 | H | C | sender | Transfer min/max bounds not enforced; `checkBook` dead | `40_transfer.rho:35-43`; `02_bounds.rho:63-74` |
| PAY-09 | H | C | sender | No web refund/history; URI not persisted | `Pay.tsx:78-80`; `web/src/lib/db.ts` |
| MKT-05 | H | C | MM, governance | `setStatus` accepts any string; no transitions | `50_market.rho:348-351` |
| MKT-07 | H | C | MM, LP | 10 terms fields hashed but unenforced | `02_bounds.rho:95-102`; `50_market.rho:467-585` |
| MKT-08 | H | C | MM, integrator | Canonical drift v4 length-prefixed vs v1 plain join | `01_kernel.rho:26-40`; `tools/market_terms.py:17,24-25`; `rcash-core/src/market.rs` |
| MKT-09 | H | C | sender, MM | wasm quote uses a keyless reader; web quotes fail | `rcash-wasm/src/lib.rs:442-456,684-693`; `v4.rs:285-306` |
| MKT-11 | H | P | MM, LP | No createMarket/Markets route/LP management/APR/NAV/lock fields | `v4.rs`; `App.tsx:21-49`; `Liquidity.tsx` |
| STB-03 | M | C | borrower, risk | Registry pause inert; vault pause mint-only | `32_currency_registry.rho:186-216`; `31_stablecoin.rho:576,618,972-993` |
| STB-04 | H | P | borrower, keeper | No vault/health/totals/liquidation client; vault view stale | `31_stablecoin.rho:916-970`; clients absent |
| STB-05 | M | P | holder | Bad debt permanent and unabsorbed | `31_stablecoin.rho:213-236` |
| STB-06 | M | P | borrower, risk | Risk parameters immutable | `31_stablecoin.rho:448-459` |
| PAY-06 | M | P | sender, receiver | No memo/reference; sender address public and reused | `40_transfer.rho:132-143` |
| PAY-07 | M | C | sender, LP | Zero slippage defaults | `Convert.tsx:19`; `v4.rs:511,547` |
| MKT-10 | M | C/P | MM, LP | Max-trade denominator, decorative minLiquidity, unburned first deposit, no maker rebate | `51_pool.rho:256-276`; `05_amm_math.rho:66`; `02_bounds.rho:47` |
| GOV-01 | M | P | all | 2-of-3 governor, no timelock | `04_governor.rho:159-163` |
| DOC-01 | L | C | all | SPEC/INTENT/INVARIANTS/README describe v0.1 or unenforced behavior | `README.md:89-97`; `docs/SPEC.md`; `docs/spec/20-INVARIANTS.md:14,66-109` |

## 10. Cross-stakeholder conflicts

| Decision | Sender | Receiver | Borrower/holder | MM/LP | Today | Recommended |
|---|---|---|---|---|---|---|
| Spread | Low | Low | Holder wants backing | LP wants yield | Sponsor-fixed | Transparent sponsor/terms plus fee tiers; no hidden protocol fee |
| Claim phlo | Low | Low | Neutral | Neutral | Receiver pays | Sponsored claim or sender pre-funds; otherwise the promise is incomplete |
| Expiry | Refund certainty | Claim certainty | Neutral | Neutral | Claim valid after expiry; race | Claim before expiry, refund after; show countdown |
| Idempotency | Retry safety | No duplicate claims | Neutral | Safe seeding | Retry double-escrows | Operation id + cached deploy |
| Privacy vs verification | Privacy | Verify amount/asset | Transparency | Transparency | Amount not measured; sender public | Measure payment on-chain; optional memo; document linkability |
| LTV/rate | Borrower high LTV/low fee | Neutral | Holder low LTV/high fee + redemption | LP safe collateral | Immutable; interest burned | Governor rate/risk params + buffer/savings/PSM |
| Pause | Exits | Exits | Safety | MM control | Governor-only; market pause inert | Pause matrix; MM-scoped pause; timelock |
| Lock control | Neutral | Neutral | Safety | Recover/cancel | Cancel pays executor | Pay funder/beneficiary; timelock |
| Liquidity lifecycle | Neutral | Neutral | Deep market | Add/remove/re-seed | Seed-only safe; full removal bricks | Standalone LP path; reset seeded; burn checks |
| Terms enforcement | Neutral | Safety | Safety | Sponsor commitments | 10 fields unenforced | Enforce or remove; one canonical encoder |

## 11. DAI comparison and the missing economics

The system has vaults, a stability fee, liquidation and AMMs. It is missing the three
components that make the DAI loop work:

| DAI component | r-cash status | Consequence |
|---|---|---|
| `vow` (surplus buffer, `sin` cancellation) | absent; interest is burned | no first-loss absorber; bad debt is permanent |
| `pot` (DSR/savings rate) | absent | stablecoin holders earn nothing; the "yield from collateral" stakeholder has no product |
| `dss-psm` (par redemption/issuance) | absent | no protocol floor/ceiling; peg relies only on AMMs and vault arbitrage |
| MKR/debt auction | absent (no governance token) | bad debt beyond the buffer is an explicit shortfall, not auctioned |

The remediation plan adds a per-currency `SurplusBuffer`, `SavingsPool` and
`PegStabilityModule` as described in the plan: split principal/interest on repay, burn only
principal, route interest to the buffer/savers, and redeem/issue stablecoin against a
governance-funded REV buffer at the oracle rate. AMMs remain the secondary venue. No new
supply is minted by the savings pool; the PSM's stablecoin is backed by its REV buffer and
counted separately from vault debt.

## 12. Remediation roadmap

**P0 — release-blocking contract fixes**
1. STB-01 repay totals; cross-block test.
2. MKT-01 pause/delist enforcement, MKT-05 transitions, STB-03 pause matrix.
3. MKT-02 reseed/burn/shares; MKT-03 cancel destination; MKT-04 fund refund.
4. PAY-05 claim expiry; PAY-08 measured payment; PAY-04 book bounds.
5. MKT-07 terms enforcement; MKT-08 v4 canonical tooling.

**P1 — economic components**
6. SurplusBuffer, SavingsPool, PSM; governor rate/savings-share/PSM domains and timelock.
7. Bad-debt accounting and mint halt when `sin > surplus`.

**P1 — client**
8. Finality-aware writes, finalized height, operation ids and cached writes.
9. Vault/health/totals/liquidation; savings and PSM screens; Markets/createMarket/LP
   management; quote fix; slippage defaults; refund/history.

**P2 — product/design**
10. Sponsored claims, memo/reference, maker rebates, OTC/RFQ, privacy improvements,
    bad-debt auction/backstop (no token decision), timelock governance.

**P3 — documentation truth**
11. Rewrite SPEC/INTENT as legacy pointers; fix INVARIANTS, README, CLIENT, FRONTEND,
    STATUS, NETWORK; add `docs/SAVINGS-AND-PSM.md`.

## 13. Static evidence appendix

- **Repay arithmetic:** with old debt `D0`, accrued `A>D0`, repayment `m`, the code writes
  vault debt `A−m` and `totalDebt = TD0−m`. The correct sum change is `(A−m)−D0`; the code
  records `−m`, omitting `A−D0`. `totalAccruedInterest` is unchanged although `A−D0` was
  accrued. Example `D0=100, A=110, m=50`: code totals 50 vs vault sum 60; TAI misses 10.
- **Canonical differential:** the on-chain v4 encoder emits `schema|len:value|...`; the
  Python/Rust tools emit a plain `|` join over the v1 30-field schema. `make measure-check`
  and `tools/market_terms.py --check` only compare their own vectors, so they do not catch
  this. The v4 harness (`harness/unit_market.py`, `unit_feed.py`) uses the correct encoding.
- **Dead control paths:** `paused` is read in `51_pool.rho:242,338` but never written;
  `TradabilityGate` is defined (`50_market.rho:366-380`) and never called; `checkBook`
  (`02_bounds.rho:63-74`) has no production caller; the registry status written at
  `32_currency_registry.rho:195-205` is not read by the issuer.
- **Client surface:** no `vault`, `totals`, `params`, `liquidate`, `createMarket`, generic
  v4 add/remove, Markets route, or web refund. The wasm quote path is keyless; the web
  journal stores activity but Pay/Claim do not use it.

## 14. Non-claims and limitations

- This is not a formal verification, an economic audit, or a mainnet-readiness statement.
- The public rhobot testnet predates the C336 merge fix and is not evidence for this review.
- The disposable devnet matrix is planned; findings marked `C` are static until the matrix
  reproduces them.
- The DAI-shaped buffer has no MKR-style debt auction; bad debt beyond the buffer remains an
  explicit shortfall.
- No exploit is claimed from a design gap; direct contract calls are still part of the
  surface even when the UI hides them.
