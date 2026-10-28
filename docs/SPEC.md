# SPEC — r-cash product specification

| | |
|---|---|
| Version | 0.5 |
| Status | Normative. Supersedes the v0.1 text previously in this file. |
| Date | 2026-10-27 |
| Conformance language | RFC 2119: MUST, MUST NOT, SHOULD, MAY |
| Formal core | `docs/spec/00-CALCULUS.md`, `10-COMPONENTS.md`, `20-INVARIANTS.md`, `30-WIRING.md` |

This document is the product specification for the whole application: contracts, clients,
web UI and operations. `docs/spec/00-30` remain normative for the component calculus,
invariants and install order; this document wins for product behaviour and client
requirements. A statement here that contradicts `00-30` is a defect in one of them and
MUST be resolved before implementation.

The non-normative design note `docs/SAVINGS-AND-PSM.md` is historical; where it differs,
this specification and `20-INVARIANTS.md` govern.

## 1. Document control

### 1.1 Requirement IDs and acceptance

Every requirement has an identifier `SPEC-<AREA>-NN`, a conformance level, an owner and a
status. Every acceptance criterion is written as a state transition or a command:

```
AC-SPEC-<AREA>-NN.k
Given <initial state>
When <actor action>
Then <exact reply or exact state delta>
```

Refusal strings are part of the interface. A test asserts the exact string. A requirement
is conformant only when every acceptance criterion passes in the final campaign.

Status values:

| Status | Meaning |
|---|---|
| `implemented` | Code exists and exhibits the behaviour; final-campaign evidence pending. |
| `planned` | Specified but not implemented, or implemented but not wired. |
| `blocked` | Cannot be completed without an upstream change; the blocker is named. |
| `excluded` | Out of scope, listed in §19. |

### 1.2 Areas

`GEN` general, `MOD` system model, `ID` identity, `PAY` payments, `ORA` oracle,
`ISS` issuance, `LIQ` liquidation, `BUF` surplus buffer, `SAV` savings, `PSM` peg,
`MKT` market lifecycle, `POOL` AMM and LP, `GOV` governance, `REG` registries,
`CLI` clients, `WEB` web UI, `OPS` operations, `INV` invariants, `EXC` exclusions.

## 2. Scope, actors and units

**Scope.** Non-custodial multi-currency accounts on rholo; claimable asset transfers;
per-currency REV-collateralised stablecoins with vaults, liquidation, a surplus buffer,
savings and a peg-stability module; AMM FX markets with locked LP seeds; a Rust
SDK/CLI/WASM and a React web client. No native code, no fiat custody, no consensus or node
changes.

**Actors.** User (account owner), recipient (claim holder), saver, vault owner, liquidator,
market maker, LP, sponsor (currency/feed/market signer), governor (2-of-3 admins),
installer, keeper (any caller of permissionless arms).

**Units.** All amounts are integer base units with 8 decimals: `100_000_000 = 1.0`.
Rates are quote-per-base in the same 8-decimal scale. Basis points are `1/10000`.
Heights are block heights. `ownerId` is the REV address derived from the owner's public
key. A payment is an ERTP holding; a purse is an ERTP name.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-GEN-01 | MUST | The product consists of the components and surfaces specified here; a surface not specified is not part of the product. | whole app | implemented |
| SPEC-GEN-02 | MUST | Every refusal returns an exact reason string from the normative list in §18.3; tests assert exact equality. | contracts | implemented |
| SPEC-GEN-03 | MUST | Documentation, manifests and Makefile targets describe the shipped behaviour only; a stale claim is a defect. | docs/ops | implemented |
| SPEC-GEN-04 | MUST | The final conformance report is keyed by requirement ID with PASS/FAIL/BLOCKED/SKIPPED; BLOCKED is never reported as conformance. | ops | planned |

## 3. System model and authority

### 3.1 Deploy semantics

A deploy is atomic. A failed deploy rolls back tuple space and native REV/ERTP state. An
arm replies exactly once. A refusal that still holds custody of a payment MUST return it
in the refusal tuple. Once value has moved (burn, ERTP withdraw, native transfer), a later
refusal MUST fail the deploy (`1/0`) rather than reply `false`, so the value movement rolls
back (invariant I15).

State is held in one cell per component. Every mutating arm follows:
peek → validate → effect → commit. A cell that a nested call in the same deploy can write
is re-read and its `rev` checked before the commit; a mismatch fails the deploy. A cell
only the arm itself writes is re-read at commit time. No cell is held consumed across an
await on a caller-supplied name.

Capabilities (`mintAuth`, `burnAuth`, `custodyAuth`, `liquidationAuth`, `settlementAuth`,
`psmMintAuth`, `psmBurnAuth`, `bufferDepositAuth`, `bufferPayAuth`, `bufferCoverAuth`,
`savingsNotifyAuth`, `directoryAuth`, `marketAuth`) live only in closure. They MUST NOT
appear in a reply, a stored map, a bundle or an attestation. Caller-supplied deposit facets
and payments are sinks, not authority (capability-provenance exception, §3.3).

### 3.2 Replies and attestations

| Arm class | Reply |
|---|---|
| Read | `(true, value)` or `(false, reason)` |
| Value-moving write | `(true, …)` with the receipt; refusal `(false, reason[, payment])` |
| Attestation | `(true, {template, currency, …immutable identity})` |

`attest` never returns a capability or a live key.

### 3.3 Requirements

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-MOD-01 | MUST | Every deploy is atomic; a failure rolls back tuple space, REV and ERTP (AC: a failing arm after a burn leaves supply unchanged). | all | implemented |
| SPEC-MOD-02 | MUST | Every arm replies exactly once; no arm leaves a caller waiting. | all | implemented |
| SPEC-MOD-03 | MUST | A refusal before any value movement returns the payment; after value movement the arm fails `1/0`. | all value arms | implemented |
| SPEC-MOD-04 | MUST | State commits revalidate the consumed cell's `rev`; a mismatch fails the deploy. | all stateful | implemented |
| SPEC-MOD-05 | MUST | Capabilities are closure-held and never returned or stored. `check_captures` passes. | all | implemented |
| SPEC-MOD-06 | MUST | Caller-supplied facets are sinks: they may receive value, never authority. | Account, TransferContract, FxPool, PSM | implemented |
| SPEC-MOD-07 | MUST | Unmatched receives are silent in Rholang; every call path either replies or is documented as fire-and-forget. | all | implemented |
| SPEC-MOD-08 | MUST | An attestation identifies template and currency and reveals no secret. | all attest arms | implemented |

## 4. Identity, accounts and purses

`AccountFactory.getOrCreate(pubKeyBytes)` derives `ownerId = revAddress(pubKey)` and returns
`(true, account, ownerId)`. It is idempotent: a second call returns the same account. The
factory creates one `Account`, one `PurseStore` and one `AccountGate` per owner. The vault
proof is created inside the account contract and never returned.

`AccountGate.verify(dId)` derives the caller's REV address and compares it to `ownerId`;
only the owner passes owner arms. `Account.depositFacet` is deliberately public and can
only receive.

`PurseStore.ensure(assetId)` resolves the issuer through `AssetResolver` and creates one
purse per asset. `deposit` measures nothing (the purse's ERTP deposit validates the
payment); `withdraw` refuses a non-positive amount; `balance` reads the purse.

`vaultOpen(dId, vaultUri)` opens (or returns) this owner's vault in the named
`VaultBook` and returns the one-shot vault capability.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-ID-01 | MUST | One account per owner; `getOrCreate` is idempotent and returns the same account and ownerId. | AccountFactory | implemented |
| SPEC-ID-02 | MUST | Owner arms require the caller's `deployerId` to derive `ownerId`; others refuse `"not owner"`. | AccountGate | implemented |
| SPEC-ID-03 | MUST | The vault proof is never returned after creation and authorises only that owner's vault. | Account, VaultBook | implemented |
| SPEC-ID-04 | MUST | A purse exists per asset at first use via `AssetResolver`; an unknown asset refuses `"unknown asset"`. | PurseStore, AssetResolver | implemented |
| SPEC-ID-05 | MUST | `depositFacet` can only receive; it cannot withdraw or act as the owner. | Account | implemented |
| SPEC-ID-06 | MUST | `deposit`/`withdraw`/`balance` use the caller's own purse only; a foreign deployer is refused. | Account, PurseStore | implemented |
| SPEC-ID-07 | MUST | REV is resolved through the native ERTP issuer, every other asset through `CurrencyRegistry` → live `Stablecoin`. | AssetResolver | implemented |
| SPEC-ID-08 | MUST | Account state is `{nextTransferId, ops, rev}`; every mutation revalidates `rev`. | Account | implemented |
| SPEC-ID-09 | MUST | `Account.transfers` returns the owner's op map for history. | Account | implemented |
| SPEC-ID-10 | MUST | Account creation and purse creation are paid by the creator; no protocol subsidy. | Account | implemented |

## 5. Payments

### 5.1 Send

`Account.sendTransfer(dId, assetId, recipientPub, amount, secretHash, expiry, memo, opId,
stipend, ret)` is owner-authenticated. It reserves `opId`, withdraws `amount` of `assetId`
into a payment, calls `TransferBook.send`, and optionally sends `stipend` native REV to the
recipient's REV address.

`TransferBook.send(senderId, id, recipientFacet, refundFacet, assetId, amount, payment,
secretHash, expiry, memo, opId, ret)`:

1. reads `bookParamsState`;
2. refuses `amount <= 0` or `amount < minAmount` with `"amount"`;
3. refuses `expiry <= now` or `expiry > now + maxExpiryBlocks` with `"expiry"`;
4. refuses a memo longer than `maxMemoBytes` with `"memo"`, an opId longer than
   `maxOpIdBytes` with `"opId"`, and a stipend above `maxStipend` with `"stipend"`;
5. measures the payment through `AssetResolver.issuer.getAmountOf` and refuses
   `actual != amount` with `"amount mismatch"`, returning the payment;
6. creates the per-transfer `TransferContract` holding the payment, stores `memo` and
   `opId`, registers it, and replies `(true, id, uri)`.

`opId` is unique per owner. An empty `opId` disables idempotency. A replay after a
completed send returns the stored `(id, uri)` without moving funds. A replay while a send
is in flight returns `(false, "pending", id)`. A refused send removes the reservation.

The stipend is optional native REV, default 0, non-refundable if unclaimed. It is sent
from the sender's deployer vault to the recipient's REV address in the same deploy so the
recipient can pay claim phlo. ERTP REV in an account purse cannot pay phlo and is not a
substitute.

### 5.2 Claim and refund

`TransferContract.claim(secret)` refuses `"expired"` when `now >= expiry`, refuses
`"bad secret"` when `claimHash(secret) != secretHash`, deposits the payment into the
recipient facet, and re-posts `{"status": "claimed"}`. `refund(dId)` refuses `"not
expired"` before expiry, refuses `"not sender"` unless the caller's REV address equals
`senderId`, deposits to the refund facet, and re-posts `{"status": "refunded"}`. A
terminal transfer refuses `"closed"`. Claim and refund race on one cell; exactly one wins.

`info` returns `{sender, asset, amount, secretHash, expiry, status, id, memo, opId,
stipend}`. The claim secret is never stored on chain.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-PAY-01 | MUST | Send measures the payment and refuses a declared/actual mismatch with `"amount mismatch"`, returning the payment. | TransferBook | implemented |
| SPEC-PAY-02 | MUST | Minimum amount, minimum expiry lead and maximum expiry are enforced from book params. | TransferBook, Bounds | implemented |
| SPEC-PAY-03 | MUST | Memo, opId and stipend bounds are enforced; refusals are `"memo"`, `"opId"`, `"stipend"`. | TransferBook, Bounds | implemented |
| SPEC-PAY-04 | MUST | A completed opId replay returns the same `(id, uri)` and moves no funds; a pending replay returns `(false, "pending", id)`. | Account | implemented |
| SPEC-PAY-05 | MUST | A refused send leaves no reservation. | Account | implemented |
| SPEC-PAY-06 | MUST | The stipend is a direct native REV transfer to the recipient's REV address, capped, non-refundable, default 0. | Account | implemented |
| SPEC-PAY-07 | MUST | Claim requires the secret preimage and an unexpired transfer; expiry is checked before the secret. | TransferContract | implemented |
| SPEC-PAY-08 | MUST | Refund requires expiry and the sender; a third party is refused `"not sender"`. | TransferContract | implemented |
| SPEC-PAY-09 | MUST | Claim and refund are mutually exclusive; the loser refuses `"closed"`. | TransferContract | implemented |
| SPEC-PAY-10 | MUST | `info` exposes memo, opId and stipend without exposing the secret. | TransferContract | implemented |
| SPEC-PAY-11 | MUST | Account history returns the owner's transfers; the web journal is the client-side copy. | Account, web | implemented |
| SPEC-PAY-12 | MUST | Book params are `{defaultExpiryBlocks, maxExpiryBlocks, minAmount, maxMemoBytes, maxOpIdBytes, maxStipend}` under `rcash:book-params:v4`. | 40_transfer, Bounds | implemented |

## 6. Oracle and feeds

### 6.1 Feed policy

`rcash:oracle-policy:v3` is `currency, k0, k1, k2, sponsor, quorum, maxAgeBlocks,
maxSpreadBps, minPrice, maxPrice, trialBlocks, trialMinSubmits`. `Bounds.checkFeed`
enforces three distinct reporter keys, sponsor in at most one slot, `quorum` in 1..3,
`trialMinSubmits >= quorum`, and the age/spread/band ranges.

Each reporter submits `(index, price, height, pubKey, sig)`. The signature is over
`rcash:oracle-submit:v3|feedId|currency|index|price|height`; the slot pubkey must match;
height must be monotonic and no more than 1000 blocks stale. `activate` requires the trial
length, minimum submissions, a quorum of reporter slots and a fresh median. `get` refuses
while paused, before activation and when the median is not fresh, with `"paused feed"`,
`"trial"`, `"stale feed"`, `"quorum"`, `"spread"` or `"band"`.

`OracleHub.getPair(base, quote, maxAgeBlocks)` returns
`(true, {rate, fresh, basePrice, quotePrice, baseAge, quoteAge})`; `rate =
floor(basePrice * 1e8 / quotePrice)`. `fresh` requires both feeds fresh and both ages
within the caller's bound. Callers enforce their own bound.

`OracleRegistry.registerFeed` requires the sponsor as deployer, the sponsor signature over
`rcash:feed-bind:v3|code|feedId|feedUri|policyHash|sponsorHex`, and a live `feed.info`
attestation matching the policy. One feed per currency; the registry is governor-gated for
reporter allowlist changes.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-ORA-01 | MUST | Exactly three distinct reporters; the sponsor occupies at most one slot; one feed per currency. | OracleRegistry, Bounds | implemented |
| SPEC-ORA-02 | MUST | Submissions are signed over the exact v3 preimage, slot-bound, monotone in height and stale-limited. | OracleFeed | implemented |
| SPEC-ORA-03 | MUST | Activation requires the trial length, minimum submissions, quorum and a fresh median. | OracleFeed | implemented |
| SPEC-ORA-04 | MUST | `get` refuses paused, trial and stale states with the exact strings. | OracleFeed | implemented |
| SPEC-ORA-05 | MUST | `getPair` computes the cross rate and per-feed ages; callers pass and enforce their own max age. | OracleHub | implemented |
| SPEC-ORA-06 | MUST | Feed binding requires the sponsor signature and the live attestation; a bad signature refuses `"bad sponsor signature"`. | OracleRegistry | implemented |
| SPEC-ORA-07 | MUST | A stale or missing rate refuses mint, withdraw, liquidate, PSM buy/sell and pool quote/swap/add; repay and exits continue. | consumers | implemented |
| SPEC-ORA-08 | MUST | Policy hash is `H(rcash:oracle-policy:v3, values)` in the length-prefixed encoding. | Codec, clients | implemented |
| SPEC-ORA-09 | MUST | Governor suspension (`setPaused`) and trial restart are immediate and domain-scoped. | OracleFeed, Governor | implemented |
| SPEC-ORA-10 | MUST | The web and clients display the feed status and ages; no client invents a price. | clients | implemented |

## 7. Stablecoin issuance

### 7.1 System creation and listing

One system per currency code. `31_stablecoin.rho` is deployed by the installer and
validates a sponsor signature over `rcash:stablecoin-create:v1|currency|paramsHash|sponsor`,
`Bounds.checkIssuer`, and `Codec.hash` of the signed params.

Issuer params are `rcash:stablecoin-params:v2`, 11 values:

```
currency, mcrBps, bonusBps, closeFactorBps, ratePerBlock, debtCeiling,
minDebt, maxDebt, maxOracleAge, savingsShareBps, psmFeeBps
```

`Bounds.checkIssuer`: `mcrBps 10000..50000`, `bonusBps 0..5000`, `closeFactorBps 1..10000`,
`ratePerBlock 0..50000`, `debtCeiling 1e10..1e15`, `minDebt 1e4..1e9`,
`maxDebt minDebt..ceiling`, `maxOracleAge 1..1000`, `savingsShareBps 0..10000`,
`psmFeeBps 0..1000`.

The deploy returns `[stablecoinUri, custodyUri, paramsUri, vaultUri, liquidationUri,
savingsUri, psmUri, bufferUri, attestation]`. `CurrencyRegistry.register` takes all eight
URIs plus the params hash and sponsor, verifies the signature over
`rcash:currency-register:v3|code|sc|custody|params|vault|liq|savings|psm|buffer|paramsHash|sponsor`,
verifies the live `attest`, and writes the entry and the `StablecoinDirectory` in one
commit.

### 7.2 Vault lifecycle

A vault is `{auth, collateral, debt, lastHeight}`. `open` returns the one-shot auth.
`deposit` accrues, adds collateral, and updates totals. `mint` accrues, checks health
(`floor(collateral * rate / 1e8) * 10000 >= debt * mcrBps`), min/max debt, ceiling and the
buffer halt, then mints. `withdraw` accrues, checks health on the reduced collateral, and
withdraws. `repay` accrues and settles (below). Interest accrues as
`ceil(debt * ratePerBlock * (now - lastHeight) / 1e12)`.

`Stablecoin.mint` refuses `"recapitalise"` when `sin > surplus`, `"max supply"` above
`maxSupply`, and `"bad mint authority"` for an unknown cap. `burn` refuses
`"bad burn authority"` and caps at the supplied maximum.

### 7.3 Repay and yield waterfall

With `delta = accrued - vault.debt`, `interestDue = delta`,
`interestPaid = min(amount, interestDue)` and `principalPaid = amount - interestPaid`:

- refuse `amount > accrued` with `"amount"`, returning the payment;
- `Stablecoin.settle(payment, principalPaid, interestPaid, settlementAuth)` burns
  `principalPaid` and deposits `interestPaid` into the `SurplusBuffer`;
- totals: `totalDebt += delta - amount`, `totalAccruedInterest += delta - interestPaid`;
- then `SurplusBuffer.cover(0, bufferCoverAuth)` and
  `SurplusBuffer.paySavings(bufferPayAuth)`, in that order, in the same deploy.

A payment of 0 principal and positive interest leaves supply unchanged and reduces unpaid
interest. `totalAccruedInterest` is net unsettled interest, not a lifetime total.

### 7.4 Views and pause

`vault(ownerId)` accrues before computing and returns `{auth-projected collateral, debt:
accrued, accruedInterest, health, rate, fresh}` without the auth. `totals` returns
`{totalDebt, totalAccruedInterest, totalCollateral, badDebt, sin, psmDebt, paused, rev}`.
`params` returns the live params and both the genesis and current hash. `pause` is the
governed currency pause; it gates `mint`, `withdraw` and PSM `buyStable` only.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-ISS-01 | MUST | One system per currency; listing binds all eight URIs in the v3 preimage. | 31_stablecoin, CurrencyRegistry | implemented |
| SPEC-ISS-02 | MUST | Params are the signed v2 11-value set; bounds and hash are enforced at creation. | Bounds, 31_stablecoin | implemented |
| SPEC-ISS-03 | MUST | `savingsShareBps` and `psmFeeBps` are seeded from the signed params. | 31_stablecoin | implemented |
| SPEC-ISS-04 | MUST | Health is required on mint and collateral withdrawal; stale or zero rate refuses `"stale feed"`/`"no rate"`. | VaultBook | implemented |
| SPEC-ISS-05 | MUST | Min/max debt, debt ceiling and max supply are enforced before minting. | VaultBook, Stablecoin | implemented |
| SPEC-ISS-06 | MUST | Interest accrues per block and is ceiled; a repay splits principal and interest via `settle`. | VaultBook, Stablecoin | implemented |
| SPEC-ISS-07 | MUST | Repay overpayment returns the payment; supply falls only by principal. | VaultBook | implemented |
| SPEC-ISS-08 | MUST | Interest reaches the buffer and the savings waterfall in the same deploy. | VaultBook, SurplusBuffer | implemented |
| SPEC-ISS-09 | MUST | The mint halt is live: `sin > surplus` refuses `"recapitalise"` and is rechecked before the ERTP mint. | Stablecoin | implemented |
| SPEC-ISS-10 | MUST | Pause gates mint, withdraw and PSM buy only; repay, liquidate, deposit, savings and redemption continue. | VaultBook, PSM | implemented |
| SPEC-ISS-11 | MUST | The vault view accrues and returns health, rate and freshness; no stale-health answer. | VaultBook | implemented |
| SPEC-ISS-12 | MUST | Risk parameters are live from `paramsState`; a governed change applies to subsequent arms. | VaultBook, PSM, RiskParameters | implemented |
| SPEC-ISS-13 | MUST | Genesis `paramsHash` is the registry identity; `currentHash` changes on a governed update. | RiskParameters, registry | implemented |
| SPEC-ISS-14 | MUST | `open` and `deposit` remain available while paused. | VaultBook | implemented |
| SPEC-ISS-15 | MUST | A vault owned by another deployer cannot be operated: `"not owner"`/`"bad vault auth"`. | VaultBook | implemented |
| SPEC-ISS-16 | MUST | Attestation identifies template and currency and reveals no capability. | Stablecoin, VaultBook, Custody | implemented |

## 8. Liquidation and bad debt

A vault is liquidatable only when unhealthy. `maxRepay = ceil(accrued *
closeFactorBps / 10000)`; a larger payment refuses `"close factor"`. Seizure is
`floor(amount * (10000 + bonusBps) * 1e8 / (rate * 10000))`. A healthy vault refuses
`"healthy"`; a stale feed refuses `"stale feed"`.

If the seizure exceeds the vault's collateral, the liquidator must repay at least the
collateral's value (`amount * 1e8 >= collateral * rate`), otherwise the arm refuses
`"underwater repayment"`; the whole collateral is seized and the vault is written off.
If the collateral is below `minCollateral`, it refuses `"slippage"`.

Write-off accounting, with `b = accrued - amount`:

- `badDebt += b` (cumulative memo);
- `SurplusBuffer.cover(b, bufferCoverAuth)` in the same deploy: `sin += b`,
  `cancelled = min(surplus, sin)`, burn `cancelled`, `sin -= cancelled`,
  `surplus -= cancelled`;
- `totalDebt -= vault.debt`, `totalAccruedInterest += delta`,
  `totalCollateral -= seized`, supply falls by the liquidator's burn;
- the vault is reset to `{collateral: 0, debt: 0}`.

**Bad debt is not a token or an auction.** It is the accounting residual a liquidation
could not recover. The buffer absorbs it; the residual `sin` blocks new minting until
interest recapitalises the buffer. There is no MKR analogue, no debt auction and no
recapitalisation token.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-LIQ-01 | MUST | Only an unhealthy vault is liquidatable, through the liquidation capability only. | VaultBook, LiquidationEngine | implemented |
| SPEC-LIQ-02 | MUST | Close factor is `ceil(accrued * closeFactorBps / 10000)`; excess refuses `"close factor"`. | VaultBook | implemented |
| SPEC-LIQ-03 | MUST | Seizure uses the bonus formula with floor; slippage below `minCollateral` refuses `"slippage"`. | VaultBook, CollateralMath | implemented |
| SPEC-LIQ-04 | MUST | Underwater repayment requires covering the collateral's value; otherwise `"underwater repayment"`. | VaultBook | implemented |
| SPEC-LIQ-05 | MUST | A write-off books `badDebt` (cumulative) and `sin` (outstanding) and clears the vault. | VaultBook, SurplusBuffer | implemented |
| SPEC-LIQ-06 | MUST | The write-off calls `cover` in the same deploy and revalidates the vault cell; a mismatch fails the deploy. | VaultBook | implemented |
| SPEC-LIQ-07 | MUST | `cover` burns `min(surplus, sin)` and leaves the residual `sin`. | SurplusBuffer | implemented |
| SPEC-LIQ-08 | MUST | New minting refuses `"recapitalise"` while `sin > surplus`. | Stablecoin | implemented |
| SPEC-LIQ-09 | MUST | A stale feed refuses liquidation; repay remains available. | VaultBook | implemented |
| SPEC-LIQ-10 | MUST | The liquidator receives the seized REV; a refusal returns the stablecoin payment. | VaultBook | implemented |
| SPEC-LIQ-11 | MUST | `totals` exposes debt, accrued interest, collateral, `badDebt` and `sin`. | VaultBook | implemented |
| SPEC-LIQ-12 | MUST | No recapitalisation token, debt auction or MKR analogue exists. | whole app | implemented |

## 9. Surplus buffer

State `{surplus, sin, savingsShareBps, rev}` plus a stablecoin purse.

- `deposit(payment, bufferDepositAuth)`: measures, deposits into the purse, `surplus +=
  amount`. Only `Stablecoin.settle` holds the cap.
- `cover(additional, bufferCoverAuth)`: accepts `additional >= 0`; `sin += additional`;
  `cancelled = min(surplus, sin)`; if `cancelled > 0`, withdraw and burn it; `sin -=
  cancelled`, `surplus -= cancelled`. `additional = 0` reconciles existing `sin` against
  new surplus.
- `paySavings(bufferPayAuth)`: `move = floor(surplus * savingsShareBps / 10000)`; if
  `move > 0` and `SavingsPool.totalShares > 0`, withdraw and `notify`; skip when the pool
  has no shares so interest is not stranded.
- `info` returns `{surplus, sin, savingsShareBps, rev}`.

Order on every interest settlement: `deposit` → `cover(0)` → `paySavings`. Solvency
before yield.

`setShare` is replaced by `scheduleShare(bps, nonce, sigs)` and `applyShare(nonce)` through
the governor timelock; `bps` is 0..10000.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-BUF-01 | MUST | Interest is deposited only through the settlement capability. | SurplusBuffer, Stablecoin | implemented |
| SPEC-BUF-02 | MUST | `cover` absorbs `min(surplus, sin)` and burns it; residual `sin` remains. | SurplusBuffer | implemented |
| SPEC-BUF-03 | MUST | `cover(0)` reconciles outstanding `sin` against new surplus. | SurplusBuffer | implemented |
| SPEC-BUF-04 | MUST | `paySavings` moves the configured share and skips an empty pool. | SurplusBuffer, SavingsPool | implemented |
| SPEC-BUF-05 | MUST | The waterfall is deposit → cover(0) → paySavings in one deploy. | VaultBook | implemented |
| SPEC-BUF-06 | MUST | Savings share changes are timelocked via the governor. | SurplusBuffer, Governor | implemented |
| SPEC-BUF-07 | MUST | `info` exposes surplus, sin and the share. | SurplusBuffer | implemented |
| SPEC-BUF-08 | MUST | No stablecoin remains counted as surplus after it is burned. | SurplusBuffer | implemented |
| SPEC-BUF-09 | MUST | Only a 2-of-3 governor can schedule or apply a share change; early execute refuses `"early"`. | Governor | implemented |
| SPEC-BUF-10 | MUST | The effective share is `floor(surplus * bps / 10000)`; no rounding in the protocol's favour. | SurplusBuffer | implemented |

## 10. Savings

State `{totalShares, totalAssets, shares: {ownerId: shares}, rev}` plus a stablecoin purse.
`ownerId` is derived from the caller's `deployerId`; a caller cannot name another owner.

- `deposit(dId, payment)`: measure; if `totalShares == 0`, `shares = amount`, else
  `shares = floor(amount * totalShares / totalAssets)`. A zero-share result refuses
  `"shares"` and returns the payment. Deposit into the purse; `totalShares += shares`,
  `totalAssets += amount`, `shares[ownerId] += shares`.
- `withdraw(dId, shares)`: require `0 < shares <= shares[ownerId]`; `amount =
  floor(totalAssets * shares / totalShares)`; withdraw and return it; decrement all.
- `notify(payment, savingsNotifyAuth)`: deposit; `totalAssets += amount`; no shares.
- `info` returns `{totalShares, totalAssets, shareValueE8, rev}` where `shareValueE8 =
  floor(totalAssets * 1e8 / totalShares)` (0 when empty). `position(ownerId)` returns the
  owner's shares and current value.

There is no lock, minimum or promised rate. A share is a claim on the pool's stablecoin
purse, not on REV collateral. The automatic yield path is §7.3/§9.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-SAV-01 | MUST | The owner is derived from `deployerId`; no arm accepts an arbitrary owner. | SavingsPool | implemented |
| SPEC-SAV-02 | MUST | First deposit is 1:1; later shares floor at `amount * totalShares / totalAssets`. | SavingsPool | implemented |
| SPEC-SAV-03 | MUST | A zero-share deposit refuses `"shares"` and returns the payment. | SavingsPool | implemented |
| SPEC-SAV-04 | MUST | Withdraw is pro-rata, floored, and bounded by the owner's shares. | SavingsPool | implemented |
| SPEC-SAV-05 | MUST | `notify` adds assets without minting shares and is capability-only. | SavingsPool | implemented |
| SPEC-SAV-06 | MUST | Interest is distributed automatically on repay; no keeper is required. | VaultBook, SurplusBuffer | implemented |
| SPEC-SAV-07 | MUST | The empty pool never receives a notify; interest stays in the buffer. | SurplusBuffer | implemented |
| SPEC-SAV-08 | MUST | `info` exposes share value; `position` exposes the owner's holding. | SavingsPool | implemented |
| SPEC-SAV-09 | MUST | No lock, minimum or promised rate exists. | SavingsPool | implemented |
| SPEC-SAV-10 | MUST | A donation cannot inflate the next depositor's cost because there is no public donation arm and the share math uses total assets. | SavingsPool | implemented |

## 11. Peg stability module

State `{stableDebt, feeBps, ceiling, rev}` plus a REV purse and a stablecoin purse.

- `fundRev(payment)`: permissionless REV donation to the PSM reserve; returns the amount.
- `buyStable(payment, stableFacet, minStable)`: measure REV;
  `gross = floor(revIn * rate / 1e8)`, `fee = ceil(gross * feeBps / 10000)`,
  `stableOut = gross - fee`. Refuse `"min stable"` below `minStable`, `"ceiling"` above
  `stableDebt + stableOut`, `"stale feed"`. Deposit the full REV; mint `stableOut` to the
  facet; `stableDebt += stableOut`.
- `sellStable(payment, revFacet, minRev)`: measure stable;
  `grossRev = floor(stableIn * 1e8 / rate)`, `feeRev = ceil(grossRev * feeBps / 10000)`,
  `revOut = grossRev - feeRev`. Refuse `"min rev"` below `minRev`, `"buffer"` above the
  REV purse, `"stale feed"`. Burn `stableIn`; withdraw and deposit `revOut`; `stableDebt
  -= stableIn`.
- Fees remain in the PSM REV purse. They are not minted to the buffer and not paid to
  savers.
- `stableDebt` is **signed**. Sell may drive it negative; that is par redemption of
  vault-issued stablecoin and is required for the peg. The only lower sanity bound is
  `-maxSupply`. The ceiling bounds the positive side.
- `buyStable` refuses while the currency is paused; `sellStable` remains available.
- `info` returns `{stableDebt, feeBps, ceiling, revBalance, rev}`; `debt` returns
  `stableDebt`.

The peg is held by arbitrage: below par, buy the stablecoin on the AMM and redeem at par
through the PSM; above par, mint at par through the PSM and sell on the AMM. The REV
buffer is finite; an empty buffer refuses redemption rather than promising fractional
cover.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-PSM-01 | MUST | `fundRev` accepts REV permissionlessly and reports the amount. | PSM | implemented |
| SPEC-PSM-02 | MUST | Buy gross floors, fee ceils, output is the difference, and the full REV is deposited. | PSM | implemented |
| SPEC-PSM-03 | MUST | Sell gross floors, fee ceils, output is the difference, and the stablecoin is burned. | PSM | implemented |
| SPEC-PSM-04 | MUST | `stableDebt` stays signed and may go negative; vault-issued stablecoin redeems at par. | PSM | implemented |
| SPEC-PSM-05 | MUST | The ceiling bounds positive debt; `ceiling >= stableDebt` is required for a policy change. | PSM | implemented |
| SPEC-PSM-06 | MUST | An empty REV purse refuses sell with `"buffer"` and returns the payment. | PSM | implemented |
| SPEC-PSM-07 | MUST | Min-output bounds refuse `"min stable"`/`"min rev"` and return the payment. | PSM | implemented |
| SPEC-PSM-08 | MUST | Fees stay in the PSM REV purse and are excluded from surplus and savings. | PSM | implemented |
| SPEC-PSM-09 | MUST | Buy is paused with the currency; sell remains available for redemption. | PSM, VaultBook | implemented |
| SPEC-PSM-10 | MUST | Fee and ceiling changes are timelocked and validated. | PSM, Governor | implemented |
| SPEC-PSM-11 | MUST | `info` exposes debt, fee, ceiling and REV balance. | PSM | implemented |
| SPEC-PSM-12 | MUST | A sell of vault-issued stablecoin produces negative `stableDebt` and preserves S3. | PSM | implemented |

## 12. AMM markets

### 12.1 Terms

The canonical schema is `rcash:market-terms:v4`, 25 values in this order:

```
marketId, slug, base, quote, version, sponsorPubKey, sponsorOwnerId,
baseFeedPolicyHash, quoteFeedPolicyHash, baseSpreadBps, skewSpreadBps,
maxTradeBps, minLiquidity, firstDepositToleranceBps, depthFloorQuote,
minTicketQuote, seedBase, seedQuote, seedInitialShares,
lockBeneficiaryPubKey, lockMinBlocks, lockUntilHeight,
bookDefaultExpiryBlocks, bookMaxExpiryBlocks, maxPairAgeBlocks
```

Encoding is length-prefixed: `schema|len(v):v|…` over UTF-8 decimal strings, hashed with
BLAKE2b-256. Rholang, Rust and Python MUST produce byte-identical strings. The sponsor
signs `rcash:market-create:v1|marketId|termsHash|sponsor`.

Every field is enforced:

| Field | Enforcement |
|---|---|
| marketId, slug | non-empty; slug unique in the index; pair key |
| base, quote | non-empty, distinct; both feeds listed and active |
| version | `>= 1`; strictly increases after a delisted version |
| sponsorPubKey | signature; equals `lockBeneficiaryPubKey` |
| sponsorOwnerId | derived from `sponsorPubKey` |
| feed policy hashes | live `OracleRegistry` entries and active feeds |
| spreads, max trade, tolerance | bounded; used by `FxPool` |
| minLiquidity | first deposit floor |
| depthFloorQuote | activation |
| minTicketQuote | swap gate |
| seedBase, seedQuote, seedInitialShares | activation lower bounds |
| lockMinBlocks, lockUntilHeight | lock funding and activation |
| book expiry fields | within global book params |
| maxPairAgeBlocks | `1..1000`; passed to the oracle |

### 12.2 Lifecycle

`MarketFactory.createMarket(terms, values, sponsor, sig)` verifies the signature, the
terms and the feeds; `PoolTemplate.create` builds the pool and lock; `MarketDirectory.bind`
and `seal`; `MarketIndex.stage` creates a `draft`. `MarketIndex.activate` requires the
sealed slot, a funded lock with `untilHeight >= lockUntilHeight`, and a pool attestation
with `seeded`, matching `termsHash`, `rb >= seedBase`,
`rq >= max(seedQuote, depthFloorQuote)` and `totalShares >= seedInitialShares`. Status is
`draft → active → paused/active → delisted`, governed and immediate.

### 12.3 Pool

`FxPool` holds base and quote purses and an LP ERTP kit. Reserves and shares change only
with ERTP deposit/withdraw in one cell. Fee is `baseSpread + |weight - 5000| * skew /
5000`; output is `floor(oracleGross * (10000 - fee) / 10000)`. `maxTradeBps` is compared
to the input reserve; `minTicketQuote` applies to the input value. The first deposit is
`floor(depositValue) - 1e8` shares and MUST be at least `minLiquidity`; the 1e8 is never
minted (documented loss).

`quote` and `swap` require an active market and a fresh oracle; `swap` passes
`TradabilityGate.admit` before any deposit. `addLiquidity` is allowed on a draft market so the seed can precede activation; it
requires a fresh oracle, enforces the seed bounds, and is refused on paused or delisted
markets. Every pre-deposit refusal returns the caller's
input payment(s); after a deposit the arm fails the deploy instead. `removeLiquidity` and `LiquidityLock.release` are the LP exit and
MUST remain available when the market is paused or delisted. Removing all liquidity sets
`seeded = false`; a later deposit reseeds.

`LiquidityLock.fund(dId, lpPayment, beneficiaryId, untilHeight)` records the funder and
beneficiary, requires `untilHeight >= now + lockMinBlocks`, and returns the payment on
refusal. `release` requires the beneficiary and the height. `cancel` is governor-gated and
requires the funder or beneficiary. A one-shot lock; a released or cancelled lock refuses
`"closed"`.

`ListingViews` exposes `currency`, `marketFor`, `market`, `isActive`, `terms`,
`currencies` and `markets`; clients discover currencies and markets through it.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-MKT-01 | MUST | Terms are the v4 25-value schema in the stated order. | Bounds, MarketTerms | implemented |
| SPEC-MKT-02 | MUST | Rholang, Rust and Python encoders are byte-identical and vectors are regenerated. | core/tools/tests | implemented |
| SPEC-MKT-03 | MUST | The sponsor signature binds marketId, termsHash and sponsor. | MarketFactory | implemented |
| SPEC-MKT-04 | MUST | Every terms field is enforced by the stated owner. | Bounds, Factory, Index, Pool | implemented |
| SPEC-MKT-05 | MUST | Slugs are unique; versions strictly increase after delisting. | MarketIndex | implemented |
| SPEC-MKT-06 | MUST | The sponsor owner is derived from the sponsor key and the lock beneficiary equals the sponsor. | MarketFactory | implemented |
| SPEC-MKT-07 | MUST | Activation checks the sealed slot, funded lock, seed base/quote and initial shares. | MarketIndex | implemented |
| SPEC-MKT-08 | MUST | Status transitions are only those in §12.2; others refuse `"transition"`. | MarketIndex | implemented |
| SPEC-MKT-09 | MUST | Paused/delisted markets refuse quote, swap and add; exit remains available. | FxPool | implemented |
| SPEC-MKT-10 | MUST | `ListingViews` enumerates currencies and markets for clients. | ListingViews | implemented |
| SPEC-MKT-11 | MUST | A market with a mismatched terms hash refuses activation and swap. | MarketIndex, FxPool | implemented |
| SPEC-MKT-12 | MUST | The factory refuses an inactive or missing feed and a mismatched policy hash. | MarketFactory | implemented |
| SPEC-MKT-13 | MUST | The AMM fee, max trade, min ticket and first-deposit tolerance match the terms. | FxPool | implemented |
| SPEC-MKT-14 | MUST | A full removal sets `seeded = false`; a later deposit reseeds. | FxPool | implemented |
| SPEC-POOL-01 | MUST | Reserves equal native custody; shares equal LP minted minus burned. | FxPool | implemented |
| SPEC-POOL-02 | MUST | First deposit mints `depositValue - 1e8` and requires `>= minLiquidity`. | FxPool | implemented |
| SPEC-POOL-03 | MUST | Quote rounds down; the pool never pays more than the oracle formula. | AmmMath, FxPool | implemented |
| SPEC-POOL-04 | MUST | `maxTradeBps` is measured against the input reserve. | FxPool | implemented |
| SPEC-POOL-05 | MUST | The tradability gate is called by swap and add, not duplicated. | FxPool | implemented |
| SPEC-POOL-06 | MUST | LP add is atomic: both payments in, shares out, or refund both. | FxPool | implemented |
| SPEC-POOL-07 | MUST | LP removal pays both assets and never strands a balance. | FxPool | implemented |
| SPEC-POOL-08 | MUST | A funded lock refuses a second fund and returns the payment. | LiquidityLock | implemented |
| SPEC-POOL-09 | MUST | Release requires the beneficiary and the height; cancel requires the funder or beneficiary. | LiquidityLock | implemented |
| SPEC-POOL-10 | MUST | A released/cancelled lock refuses `"closed"`. | LiquidityLock | implemented |

### 12.4 Currency mesh, USD default and external assets

The DEX is a **full mesh of direct pairs**, not a hub and not a router. One
`FxPool` serves an unordered pair in both directions; `byPair` records both
orientations and `marketFor` resolves either one. The supported currency set is
versioned in `configs/mesh.json`; the protocol itself accepts any registered
currency and any direct pair.

USD is the default display, account and new-market quote currency. The native
R-Cash USD system is the default USD unit. A user may select a different default
in the client; no on-chain preference state exists. External DAI/USDC/USDT-style
assets are registered through the external-asset adapter interface in
`docs/spec/EXTERNAL-ASSETS.md` and trade as separate codes with their own feeds.

Pair creation is permissionless. The launch set (`configs/mesh.json`) is the
discovery source for supported currencies and priority pairs; priority pairs are
created and seeded at launch, and an unlisted supported pair shows as unavailable
until a sponsor/LP creates it. The web client shows a mesh matrix with
`active`, `draft` and `unlisted` states and an indicative oracle cross-rate even
when no pool exists.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-DEX-01 | MUST | The DEX supports direct markets for every supported ordered lookup, with exactly one active-or-paused market per unordered pair. | MarketIndex, MarketFactory | planned |
| SPEC-DEX-02 | MUST | `byPair` records both orientations and `marketFor(base, quote)` resolves either orientation to the same market. | MarketIndex, ListingViews | planned |
| SPEC-DEX-03 | MUST | USD is the default display, account and new-market quote currency; a client MAY override the default per user with no on-chain state. | Web, SDK, CLI | planned |
| SPEC-DEX-04 | MUST | The native R-Cash USD system is listed like any other currency; it is the default USD unit. | CurrencyRegistry, mesh config | planned |
| SPEC-DEX-05 | MUST | An external asset is registered only through `registerExternal`, with a sponsor signature, an adapter attestation, `kind: external` and `decimals: 8`. | CurrencyRegistry, AssetResolver | planned |
| SPEC-DEX-06 | MUST | An external asset has no VaultBook, PSM, savings or liquidation; stablecoin-only screens filter it out. | Web, SDK | planned |
| SPEC-DEX-07 | MUST | `MarketIndex.pauseAsset` is governor-authorised and pauses every active market containing the code. | MarketIndex, Governor | planned |
| SPEC-DEX-08 | MUST | Priority pairs from `configs/mesh.json` are created and seeded at launch; other supported pairs remain permissionless and show unavailable until created. | mesh tooling, ListingViews | planned |
| SPEC-DEX-09 | MUST | The mesh matrix exposes every supported pair, its market state and an indicative oracle rate. | Web, ListingViews | planned |
| SPEC-DEX-10 | MUST | A bridged USD asset is priced by its own feed; the DEX does not assume a 1.0 peg for an external code. | OracleHub, FxPool | planned |

## 13. Governance, timelock and pause

### 13.1 Admin authority

`Root` holds `installer`, `admins`, `threshold: 2`, `frozen`, `entries`. `Governor` holds
the admin set, threshold, per-domain nonces, `timelock: 100` blocks and `pending`.

`authorize(domain, nonce, action, argsHash, sigs)` verifies 2-of-3 over
`rcash:admin:v1|domain|nonce|action|argsHash`, enforces the per-domain nonce and consumes
it. `schedule(domain, nonce, action, argsHash, args, sigs)` stores
`pending[domain|nonce] = {action, argsHash, args, readyAt: height + timelock}`.
`execute(domain, nonce)` refuses `"unknown"` or `"early"`, rechecks the args hash and
returns `(true, action, argsHash, args)`. `pending(domain, nonce)` is a view.

Timelocked actions: risk params (`setRiskParams`), savings share (`setSavingsShare`), PSM
policy (`setPsmPolicy`), market status transitions, lock cancel. Immediate: currency pause
(emergency), oracle pause/trial restart, admin/threshold/timelock changes (governor domain).

### 13.2 Pause matrix

| Action | Currency paused | Market paused/delisted | Feed stale |
|---|---|---|---|
| Account deposit/withdraw/balance | allowed | allowed | allowed |
| Transfer send/claim/refund | allowed | allowed | allowed |
| Vault open/deposit | allowed | allowed | allowed |
| Vault mint | refused `"paused"` | allowed | refused `"stale feed"` |
| Vault withdraw | refused `"paused"` | allowed | refused `"stale feed"` |
| Vault repay | allowed | allowed | allowed |
| Vault liquidate | allowed | allowed | refused `"stale feed"` |
| PSM buy | refused `"paused"` | allowed | refused `"stale feed"` |
| PSM sell | allowed | allowed | refused `"stale feed"` |
| Savings deposit/withdraw | allowed | allowed | allowed |
| Pool quote/swap/add | allowed | refused `"not active"` | refused `"stale feed"` |
| Pool remove / lock release | allowed | allowed (exit) | allowed |

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-GOV-01 | MUST | Admin actions require 2-of-3 over the exact domain preimage and a monotone nonce. | Governor, AdminGuard | implemented |
| SPEC-GOV-02 | MUST | Timelocked actions are scheduled, executed after 100 blocks, and recheck the args hash. | Governor | implemented |
| SPEC-GOV-03 | MUST | Early execute refuses `"early"`; unknown refuses `"unknown"`; replay refuses `"replay"`. | Governor | implemented |
| SPEC-GOV-04 | MUST | Risk params, savings share and PSM policy are timelocked; pause and market status are immediate. | Governor, contracts | implemented |
| SPEC-GOV-05 | MUST | The pause matrix in §13.2 is the complete matrix; any other refusal is a defect. | all | implemented |
| SPEC-GOV-06 | MUST | `pending` exposes scheduled actions for clients. | Governor | implemented |
| SPEC-GOV-07 | MUST | A governed params change applies to subsequent arms and does not rewrite the genesis hash. | RiskParameters | implemented |
| SPEC-GOV-08 | MUST | Root freeze is terminal; a frozen root refuses further registration. | Root | implemented |
| SPEC-GOV-09 | MUST | Currency pause is reported in the registry entry for clients and enforced by the issuer. | CurrencyRegistry, VaultBook | implemented |
| SPEC-GOV-10 | MUST | Market status is the sole pool pause authority; no dead `poolState.paused` field exists. | FxPool, MarketIndex | implemented |

## 14. Registries and wiring

`Root` is the only singleton directory. Per-instance URIs live in
`CurrencyRegistry`/`StablecoinDirectory`, `OracleRegistry`, `MarketDirectory` and the
`ListingViews` projection. Install order is `Root → AdminGuard → Clock/Verifier/Codec →
Bounds → Governor → AmmMath → CollateralMath → OracleMath → ClaimCode → OracleRegistry →
OracleHub → CurrencyRegistry → AssetResolver → TransferBook → PoolTemplate → Market* →
AccountFactory`. Each step registers in Root; the installer verifies the keys at the
carrying block before the next step.

A stablecoin entry stores `{kind: stablecoin, stablecoinUri, custodyUri, paramsUri,
vaultUri, liquidationUri, savingsUri, psmUri, bufferUri, paramsHash, sponsor, status}`.
An external entry stores `{kind: external, assetUri, decimals: 8, sponsor, status}` and has
no issuer, vault, PSM or savings URIs.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-REG-01 | MUST | Root registration is installer-signed; rotation/freeze are 2-of-3 and versioned. | Root | implemented |
| SPEC-REG-02 | MUST | Exactly one system per currency; duplicate listing refuses `"currency exists"`/`"duplicate"`. | CurrencyRegistry | implemented |
| SPEC-REG-03 | MUST | Currency registration binds all eight URIs plus params hash and sponsor in the v3 preimage. | CurrencyRegistry | implemented |
| SPEC-REG-04 | MUST | The directory is written only after the live attestation matches. | CurrencyRegistry | implemented |
| SPEC-REG-05 | MUST | Asset resolution is per-call; no registry capability is cached in a bundle. | AssetResolver | implemented |
| SPEC-REG-06 | MUST | Install order matches §14 and each step's Root keys resolve before the next. | installers | implemented |
| SPEC-REG-07 | MUST | `ListingViews` resolves components at arm entry and never caches. | ListingViews | implemented |
| SPEC-REG-08 | MUST | The manifest lists every component URI and no capability or key. | rcash-core, ops | implemented |
| SPEC-REG-09 | MUST | A stale registry status is corrected by a governed pause, not by the issuer reading the registry. | CurrencyRegistry, VaultBook | implemented |
| SPEC-REG-10 | MUST | The contract catalogue matches the built terms and arm lists. | components.json | implemented |
| SPEC-REG-11 | MUST | An external asset is listed only by `registerExternal` with a sponsor signature, an adapter attestation and `decimals: 8`. | CurrencyRegistry, AssetResolver | planned |
| SPEC-REG-12 | MUST | An external entry carries no R-Cash issuer system and is filtered out of Vault/Earn/Redeem. | CurrencyRegistry, web | planned |

## 15. Clients (Rust SDK, CLI, WASM)

The Rust SDK is the single client logic source; the CLI and WASM are thin surfaces.
Amounts are parsed as decimal strings to 8 decimals; heights are integers; no float
arithmetic. Trusted inputs are hex bytes, lengths and base units.

- Reads: currencies, markets, terms, reserves, slots, locks, supply, transfers, balances,
  vault/health/totals/params, savings info/position, PSM info, buffer info, risk params,
  governor pending, account transfers.
- Writes: vault open/deposit/mint/repay/withdraw/liquidate; savings deposit/withdraw; PSM
  buy/sell; send (memo/opId/stipend), claim, refund; market create/activate/status; pool
  add/remove/swap/release; currency pause; governor schedule/execute; buffer/PSM/risk
  schedule/apply.
- Freshness-gated reads require the signing client; a locked wallet returns `"unlock to
  quote"` rather than a zero price.
- Writes report success only at a finalized block that does not list the deploy in
  `rejectedDeploys`. Expiry anchors to the finalized height, never the non-final tip.
- Native writes use the write-ahead op cache (`deploy_term_cached`) and retries reuse the
  same signed body. WASM uses the on-chain `opId` plus the IndexedDB journal.
- Slippage minima are explicit parameters. The CLI defaults to 50 bps from the quote and
  refuses a zero minimum for swap, add and remove.
- USD is the default display, account and new-market quote; `--display-currency` /
  `RCASH_DISPLAY_CURRENCY` overrides it for human output, and the web stores the choice in
  localStorage. No on-chain preference state exists.
- `v4 currencies` reports `kind` and, for an external asset, `assetUri`, `decimals`, `chain`
  and `custodian`. `v4 market` resolves either orientation of an unordered pair.
- Errors map to the refusal taxonomy; 429/503/admission/duplicate/term-too-large exit with
  the documented code and never masquerade as a protocol refusal.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-CLI-01 | MUST | SDK, CLI and WASM expose every user-facing arm in §15. | SDK/CLI/WASM | implemented |
| SPEC-CLI-02 | MUST | Amounts are exact base units; no floats; parsing refuses >8 decimals. | rcash-core | implemented |
| SPEC-CLI-03 | MUST | Freshness-gated reads use the signing client; locked wallets refuse clearly. | SDK/WASM | implemented |
| SPEC-CLI-04 | MUST | Success requires finality and absence from `rejectedDeploys`. | SDK | implemented |
| SPEC-CLI-05 | MUST | Retries are idempotent: native op cache or on-chain opId. | SDK | implemented |
| SPEC-CLI-06 | MUST | Expiry anchors to the finalized height. | SDK | implemented |
| SPEC-CLI-07 | MUST | Swap/add/remove defaults are non-zero (50 bps) and explicit. | CLI/web | implemented |
| SPEC-CLI-08 | MUST | The CLI exposes vault, savings, PSM, buffer, markets and governance commands. | CLI | implemented |
| SPEC-CLI-09 | MUST | WASM exports the same methods with camelCase JSON and exact string amounts. | WASM | implemented |
| SPEC-CLI-10 | MUST | `make demo` runs a real send → claim journey. | CLI | implemented |
| SPEC-CLI-11 | MUST | Error classes are distinguishable and documented. | SDK | implemented |
| SPEC-CLI-12 | MUST | V4Currency carries kind and, for stablecoins, custody/params/liquidation/savings/PSM/sponsor URIs. | SDK/WASM/web | implemented |
| SPEC-CLI-13 | MUST | USD is the default display/account/new-market quote and a client may override it. | SDK/CLI/WASM/web | planned |
| SPEC-CLI-14 | MUST | A client can read an external asset's kind, provenance and decimals. | SDK/WASM/web | planned |

## 16. Web UI

The web client is non-custodial: the private key lives only in WASM; the browser stores an
encrypted keystore and public state. Secrets never enter localStorage.

Routes: Accounts, Receive, Convert, Pay, Claim, Vault, Earn, Redeem, Markets, Market
detail, Market create, Liquidity, History, Governance (read-only), Settings. Batch and
Ramps remain disabled and are named as exclusions.

| Screen | Required behaviour |
|---|---|
| Accounts | REV + per-asset balances; a total in the preferred currency (USD by default); faucet; fund REV; currency list from the chain; copy key/address; no hard-coded asset list. |
| Receive | Public key/address; open a claim link; no secret display beyond the fragment. |
| Pay | Asset picker; amount; recipient pubkey; expiry from finalized height; memo; opId generated and journaled before send; stipend with non-refundable warning; claim link; refund of expired sends. |
| Claim | Status, expiry countdown, stipend, memo; claim disabled unless open and unexpired; REV-for-phlo warning. |
| Vault | Per-currency collateral, debt, accrued interest, health, liquidation price; deposit, mint, repay, withdraw; totals; keeper liquidation. |
| Earn | Savings share value, position, deposit/withdraw, yield to date. |
| Redeem | PSM info, buy/sell, fee, ceiling, signed debt; explains par redemption and the finite buffer. |
| Markets | Currency mesh matrix with `active`/`draft`/`paused`/`unlisted` states; USD default quote; create with the 25-field form and validation; activate; swap; add/remove liquidity; seed + lock countdown; reserves. |
| Liquidity | Existing market slot, lock countdown, add/release, non-zero minima. |
| History | Journal + on-chain transfer status; pending reconciliation on boot. |
| Governance | Read-only admin set, pending actions and timelock state. |
| Settings | Node, manifest, preferred display currency (USD default), keystore export, lock. |

The IndexedDB journal records every write before submission, with transfer URI, asset,
amount, expiry, opId, recipient and status. Pending entries are reconciled on boot.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-WEB-01 | MUST | Every user-facing arm in §15 has a screen or an explicit CLI-only note. | web | implemented |
| SPEC-WEB-02 | MUST | The private key never leaves WASM; the keystore is encrypted; no secret in localStorage. | store/wasm | implemented |
| SPEC-WEB-03 | MUST | Amounts use exact BigInt formatting; no float arithmetic. | format.ts | implemented |
| SPEC-WEB-04 | MUST | Slippage minima are derived from the quote, default 50 bps, editable, never zero. | Convert/Liquidity/Markets | implemented |
| SPEC-WEB-05 | MUST | Send journals before submit and reconciles pending entries. | Pay/db.ts | implemented |
| SPEC-WEB-06 | MUST | opId is generated per send and reused on retry. | Pay | implemented |
| SPEC-WEB-07 | MUST | Memo and stipend are exposed with the non-refundable warning. | Pay | implemented |
| SPEC-WEB-08 | MUST | Expiry uses the finalized height. | Pay | implemented |
| SPEC-WEB-09 | MUST | Claim shows status, expiry and stipend; refund is available for expired sends. | Claim/History | implemented |
| SPEC-WEB-10 | MUST | Vault, Earn, Redeem and Markets screens exist with the behaviours above. | new routes | implemented |
| SPEC-WEB-11 | MUST | Currencies are discovered from the chain, not `DEFAULT_ASSETS`. | Accounts | implemented |
| SPEC-WEB-12 | MUST | A locked wallet shows "unlock to quote" for freshness-gated reads. | Convert/Liquidity | implemented |
| SPEC-WEB-13 | MUST | Batch and Ramps are disabled with an accurate reason. | Disabled | implemented |
| SPEC-WEB-14 | MUST | The journal never stores a claim secret or a private key. | db.ts | implemented |
| SPEC-WEB-15 | MUST | The preferred currency defaults to USD and is user-selectable in Settings; no secret is stored with it. | preferences.ts, Settings | planned |
| SPEC-WEB-16 | MUST | Accounts shows a preferred-currency total and per-asset converted values, or "no price" when a feed is missing. | Accounts | planned |
| SPEC-WEB-17 | MUST | Markets shows the full supported mesh with availability and an indicative oracle rate; external assets are labelled. | Markets | planned |

## 17. Operations

- A devnet is a fixed-node rholo image with one validator for unit campaigns and four for
  merge arms. The node commit and image digest are recorded with every campaign.
- Keys are generated once. `make keys` is idempotent: it reuses an existing keystore and
  only `--fresh` regenerates. The deployer is validator 0 and is funded at genesis.
- The faucet drips 0.3 REV, is rate-limited and idempotent below the drip. A fresh chain
  funds every non-deployer key before the first suite.
- `make install FRESH=1` deploys the 17-step kernel and writes the manifest only after
  every step resolves. `make bootstrap` deploys the demo currencies, feeds and market and
  writes `deployments/devnet-v4.systems.json`.
- `deployments/devnet-v4.json` is the component manifest (23 fields, no nulls).
  `testnet-v4.json` is annotated as incomplete until the public testnet completes.
- `configs/mesh.json` is the tracked source for the supported currency set, majors,
  USD default and priority pairs. `make mesh-plan` validates it; `make mesh-install`
  deploys the native systems and feeds and seeds the priority pairs on a fresh devnet;
  `make mesh-pair BASE=... QUOTE=...` creates a non-priority pair. The full mesh remains
  permissionless; only priority pairs are seeded at launch.
- A bridged asset is listable only after a bridge or custodian deploys an 8-decimal ERTP
  adapter; the mesh install refuses an enabled external entry without an `adapterUri`.
- A failed deploy is never retried blind; the client classifies refusal, duplicate and
  finality.
- 1 GiB hosts and public-testnet completion are not conformance targets.

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-OPS-01 | MUST | Fresh devnet, install and bootstrap are reproducible from documented commands. | Makefile/harness | implemented |
| SPEC-OPS-02 | MUST | Keys are idempotent; regeneration requires `--fresh`. | keygen | implemented |
| SPEC-OPS-03 | MUST | The installer verifies every step before the next and writes no partial manifest. | installers | implemented |
| SPEC-OPS-04 | MUST | Manifests contain no nulls on a completed install and no capabilities. | ops | implemented |
| SPEC-OPS-05 | MUST | Campaigns record source SHA, image digest, prefix, memory and timestamps. | ops | planned |
| SPEC-OPS-06 | MUST | The faucet and deployer budgets are documented and respected. | ops | implemented |
| SPEC-OPS-07 | MUST | Public-testnet and merge-gossip arms are reported BLOCKED, never green. | ops | planned |
| SPEC-OPS-08 | MUST | Docs, Makefile and manifests describe the shipped behaviour. | docs | implemented |
| SPEC-OPS-09 | MUST | `unit-all` is the ordered campaign list. | Makefile | implemented |
| SPEC-OPS-10 | MUST | The demo journey runs end to end on the bootstrapped devnet. | CLI | implemented |
| SPEC-OPS-11 | MUST | `make mesh-plan` validates the tracked mesh config before any deployment. | tools/mesh.py | implemented |
| SPEC-OPS-12 | MUST | `make mesh-install` deploys the native currencies, feeds and priority pairs; an external entry without an adapter is refused. | tools/mesh.py | planned |

## 18. Invariants and conformance

### 18.1 Normative invariants

`docs/spec/20-INVARIANTS.md` is the sole normative invariant text: I1–I15 and I19–I24, plus S1–S12, with
S3 revised to:

```
totalDebt + sin + psmDebt = supply + totalAccruedInterest
```

`totalAccruedInterest` is net unsettled interest. `sin` is outstanding bad debt net of
surplus. `psmDebt` is signed. `badDebt` is a cumulative memo outside the identity.

### 18.2 Compliance

| ID | Level | Requirement | Owner | Status |
|---|---|---|---|---|
| SPEC-INV-01 | MUST | Every requirement maps to at least one invariant or is a pure client/ops requirement. | spec | implemented |
| SPEC-INV-02 | MUST | S1–S12 and I1–I15/I19–I24 hold; S3 uses the revised identity. | contracts | implemented |
| SPEC-INV-03 | MUST | The final report traces each requirement to its evidence and states PASS/FAIL/BLOCKED/SKIPPED. | ops | planned |

### 18.3 Refusal strings

```
action  age  already active  amount  amount mismatch  asset  asset mismatch  bad attestation
bad buffer authority  bad burn authority  bad custody authority  bad directory authority  bad index
bad index authority  bad liquidation authority  bad mint authority  bad savings authority
bad secret  bad settlement authority  bad signature  bad sponsor  bad sponsor signature
bad vault auth  bad version  balance  band  base feed  base feed policy  base spread  below MCR
below threshold  bonus  book expiry  bps  buffer  burn  ceiling  changed  close  close factor
closed  currency mismatch  custody  default expiry  deposit  depth  depth floor  duplicate  early
exists  expired  expiry  external attestation  external decimals  external kind  feed attestation
feed inactive  feed info  first deposit balance  frozen  funded  future price  healthy  height
height not monotonic  lock beneficiary  lock height  lock too short  lock unfunded  locked  max debt
max expiry  max memo  max op id  max stipend  max supply  max trade  mcr  memo  min amount  min debt
min liquidity  min rev  min stable  min ticket  minimum  no account  no attestation  no currency
no feed  no lock  no market  no purse  no rate  no slot  no system  no terms  no vault  not LP
not a REV payment  not a stablecoin payment  not active  not an LP payment  not base
not beneficiary  not draft  not expired  not funder  not installer  not owner  not quote
not reporter  not sealed  not seeded  not sender  not this asset  opId  oracle age  output  pair
pair active  params hash  paused  payment  pending  psm fee  psm floor  quorum  quote feed
quote feed policy  rate  recapitalise  replay  reporter not allowlisted  reporters  retired
savings share  sealed  seed mismatch  shares  shares mismatch  skew  slippage  slug
sponsor mismatch  sponsor owner  sponsor slots  spread  stale  stale feed  stale submit  stipend
supply  terms fields  terms mismatch  threshold  timelock  tolerance  transition  trial
trial submits  underwater repayment  unfunded  unknown  unknown admin action  unknown asset
unknown component  verify failed  version
```

The list is generated from the deploy inventory (reply-position string literals) and
is checked against every flow transition by `tools/check_flows.py`. A new refusal
string is a spec change and requires an entry here; `docs/spec/flows/REFUSAL-DECISIONS.md`
records the decision for each one.

## 19. Exclusions

| ID | Excluded | Reason |
|---|---|---|
| SPEC-EXC-01 | Batch payouts | Not in the protocol; separate deploys are not atomic. |
| SPEC-EXC-02 | Ramp registry / fiat ramps | No custody or fiat integration. |
| SPEC-EXC-03 | CPMM / router / multi-hop | Direct pairs only; the full mesh is the alternative to a router. |
| SPEC-EXC-04 | Cards, platform API | Out of product scope. |
| SPEC-EXC-05 | MetaMask signing | Spike not run; no decision. |
| SPEC-EXC-06 | OTC / RFQ / limit orders | Not implemented. |
| SPEC-EXC-07 | Public-testnet completion | Upstream 1 GiB / node issue; blocked. |
| SPEC-EXC-08 | Merge-gossip arms | Upstream devnet limitation; blocked. |
| SPEC-EXC-09 | 1 GiB pressure testing | Out of scope by decision. |
| SPEC-EXC-10 | Recapitalisation token / debt auction / MKR analogue | Separate workstream. |
| SPEC-EXC-11 | Sponsored (meta-transaction) claims | Stipend is a reimbursement, not phlo pre-payment. |
| SPEC-EXC-12 | Maker rebates | Deferred. |
| SPEC-EXC-13 | Encrypted memo | Plaintext bounded memo only. |
| SPEC-EXC-14 | Governance writes in the web UI | CLI/ops only; the web is read-only for governance. |
| SPEC-EXC-15 | Direct-delivery transfers | Claim-link transfers only. |

## 20. Traceability

| Area | Contract | SDK / CLI / WASM | Web | Campaign suites |
|---|---|---|---|---|
| ID | `09_identity.rho` | `v4_balance`, account reads | Accounts, Receive | unit-accounts |
| PAY | `40_transfer.rho`, `09_identity.rho` | `v4_send_transfer`, claim/refund, transfers | Pay, Claim, History | unit-transfer, unit-transfer-memo |
| ORA | `31_feed.rho`, `12/13` | oracle reads | Markets (status) | unit-feed, unit-hub |
| ISS | `31_stablecoin.rho`, `32_currency_registry.rho` | `v4_vault_*`, currency | Vault | unit-stablecoin, unit-interest |
| LIQ | `31_stablecoin.rho` | `v4_liquidate`, vault views | Vault (keeper) | unit-liquidation, unit-buffer |
| BUF | `31_stablecoin.rho` | buffer info, schedule/apply | Earn (info) | unit-buffer, unit-timelock |
| SAV | `31_stablecoin.rho` | savings methods | Earn | unit-savings, unit-interest |
| PSM | `31_stablecoin.rho` | PSM methods | Redeem | unit-psm |
| MKT/POOL | `50_market.rho`, `51_pool.rho` | market/pool methods | Markets, Liquidity | unit-market, unit-pool |
| GOV | `04_governor.rho`, contracts | governance commands | Governance (read) | unit-timelock, unit-v3 |
| REG | `00_root.rho`, `32`, `14` | manifest/currency reads | Settings | unit-v3 |
| CLI | crates | all | wasm | cargo test, wasm smoke |
| WEB | web | wasm | all routes | vitest, Playwright |
| OPS | harness, Makefile | CLI | — | install, bootstrap, demo |
