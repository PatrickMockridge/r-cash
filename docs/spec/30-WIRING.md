# 30 — Wiring, bootstrap and lifecycle

## 1. Root and resolution

`Root` is the only singleton directory. Its state is

```
rootState = {
  installer: Bytes,
  frozen: Bool,
  entries: Map<String, {uri: String, version: Int, kind: String, status: String}>
}
```

- `register(key, uri, version, kind)` is available only while `!frozen`. During bootstrap it
  authenticates the deploy's `deployerId` public key against `installer`. A deploy that
  creates a random URI with `insertArbitrary` cannot be pre-signed, so `deployerId`
  authentication is the bootstrap mechanism.
- `rotate(key, expectedVersion, newUri, newVersion, sigs)` requires the expected version and
  an admin threshold signature over `(key, expectedVersion, newUri, newVersion)`. It is
  available only while `!frozen`.
- `deprecate` marks an entry `retired`; reads still return it with a status so old clients
  can drain, writes refuse.
- `freeze` is terminal: it blocks `register`, `rotate`, `deprecate` and `admin`. A future
  upgrade publishes a successor `Root` and the client manifest switches URI.

Every deploy carries `__ROOT_URI__` as a string literal and stable key strings. It never
captures a capability returned by `resolve`. The cold-path helper is:

```
resolve(key) -> (uri, version) | (false, reason)
lookup(uri)  -> cap
```

Resolution happens at arm entry, before any consume or value movement. An unknown key or a
retired entry is a refusal, not a silent wait. No resolved capability is cached across
arms; a URI string may be cached only for an immutable singleton.

## 2. Factories and directories

A factory and its directory are co-deployed in one term. Each holds the other's locally
created capability in its closure, so no live capability crosses a deploy.

| Factory | Directory | Writes |
|---|---|---|
| `CurrencyRegistry` (signed system deploy) | `StablecoinDirectory` | `currency → {stablecoinUri, custodyUri, paramsUri, vaultUri, liquidationUri, savingsUri, psmUri, bufferUri, paramsHash, sponsor, status}` |
| `MarketFactory` | `MarketDirectory` | `marketId → {poolUri, lockUri, termsHash}` |

There is no separate stablecoin factory in v0.4: `31_stablecoin.rho` verifies the sponsor
signature, bounds and params hash before creating the system, so the deploy is the creation
gate. `CurrencyRegistry` verifies the live attestation and writes the directory; the
directory's only write capability is in the registry's closure. The system deploy creates
the issuer, custody, vault book, liquidation engine, risk parameters, savings pool, surplus
buffer and PSM in one term, because the mint/burn/settlement/purse capabilities cannot
cross a deploy boundary.

`OracleFeed` is deployed per currency by its sponsor; `OracleRegistry.registerFeed` binds
the URI after the sponsor signature and feed attestation check. There is no feed factory.

The factory is the only writer. A caller cannot supply a pool, book, lock, stablecoin or feed.
The sponsor signs the economic terms, not an arbitrary contract URI. `MarketDirectory`
accepts draft binds and a final `seal`; a sealed slot is immutable for that market version.

`Governor` owns the admin set, threshold, per-domain nonce, timelock and pending actions. A
unit with an immediate arm calls `Governor.authorize(domain, nonce, action, argsHash,
sigs)`, receives the verified intent, and applies it locally. A parameter change calls
`Governor.schedule(domain, nonce, action, argsHash, args, sigs)`; after `timelock` blocks,
any caller invokes `Governor.execute(domain, nonce)`, which rechecks the args hash and
returns the intent for the owning contract to validate and apply. The governor's nonce is
the replay ledger; an action that fails after authorization is lost, which is a liveness
cost, not a safety defect. Emergency pause and market status transitions use `authorize`
and remain immediate.

## 3. Bootstrap order

Each line is one deploy, anchored at the current tip, independently retryable, and followed
by a block boundary before the next.

| Step | Deploy | Registers |
|---|---|---|
| 00 | `Root` | `rcash:root` |
| 01 | `Clock`, `Verifier`, `Codec` | `component:clock`, `component:verifier`, `component:codec` |
| 02 | `Bounds`, `AdminGuard`, `AmmMath`, `OracleMath`, `ClaimCode` | `component:*` |
| 03 | `Governor` | `component:governor` |
| 07 | `OracleRegistry` | `component:oracle-registry` |
| 08 | `OracleHub` | `component:oracle-hub` |
| 09 | `CurrencyRegistry` + `StablecoinDirectory` | `component:currency-registry`, `component:stablecoin-directory` |
| 10 | `AssetResolver` | `component:asset-resolver` |
| 10b | `TransferBook` | `component:transfer-book` |
| 10c | `PoolTemplate` | `component:pool-template` |
| 10d | `MarketTerms`, `MarketIndex`, `MarketDirectory`, `MarketFactory`, `TradabilityGate`, `ListingViews` | `component:market-*`, `component:tradability-gate`, `component:listing-views` |
| 11 | `AccountFactory` (creates `Account`, `PurseStore`, `AccountGate` per owner) | `component:account-factory` |
| 12 | per currency: deploy `31_stablecoin` with signed params v2, then `CurrencyRegistry.register` with the sponsor signature and all seven URIs | `currency:<CODE>` |
| 12b | per currency: `OracleFeed`, then `OracleRegistry.registerFeed` | `feed:<CODE>` |
| 13 | per market: `MarketFactory.createMarket`, seed, lock, activate | `market:<PAIR>:vN` |
| 99 | `Root.freeze` | — |

The installer writes `deployments/devnet-v4.json` only after the final step. Each step
records the deploy id, block hash, block number, URIs, measured bytes/depth and phlo. A
failed step aborts the install; it never writes a half-installed manifest.

## 3b. Currency listing and liquidation

Listing is evidence-first and idempotent per code:

1. The sponsor deploys `31_stablecoin` with the canonical params v2, hash and signature; the
   deploy refuses a bad signature, out-of-bounds params, a hash mismatch or a duplicate
   system for the code (the registry check below is the authoritative duplicate gate).
2. `CurrencyRegistry.register(code, scUri, custodyUri, paramsUri, vaultUri, liqUri,
   savingsUri, psmUri, bufferUri, paramsHash, sponsor, sig)` verifies
   `rcash:currency-register:v3|code|scUri|custodyUri|paramsUri|vaultUri|liqUri|savingsUri|psmUri|bufferUri|paramsHash|sponsor`,
   calls the live `Stablecoin.attest`, and requires the currency, params hash and sponsor to
   match. It then writes `StablecoinDirectory` and the currency record in one commit.
3. A duplicate code is refused before the signature check; a bad signature is refused before
   the directory write. `setPaused` is governor-gated per domain `stablecoin:<CODE>`, calls
   `VaultBook.pause`, and mirrors the status in the registry only after the issuer accepts.

Liquidation is permissionless but capability-bound:

1. A liquidator takes a stablecoin payment and calls `LiquidationEngine.liquidate(ownerId,
   payment, minCollateral)`.
2. The VaultBook accrues interest, rejects a healthy vault, bounds the repayment by
   `ceil(debt · closeFactorBps / 10000)` and computes the seizure with `CollateralMath.payout`.
3. If the vault cannot cover the bonus slice, clearing is allowed only when the repayment
   covers the collateral's value; the residual is booked to `badDebt` (cumulative memo) and
   `sin` (outstanding), and the vault debt is cleared.
4. The write-off calls `SurplusBuffer.cover(residual)`, which burns `min(surplus, sin)`; the
   vault cell is revalidated after the cover and a `rev` mismatch fails the deploy so the
   burn and cover roll back together.
5. The burn and custody withdrawal happen before the single vault/totals commit. Any refusal
   aborts the deploy, so a half-settled liquidation cannot persist. Refusals before the
   consume return the payment to the caller. New minting refuses `"recapitalise"` while
   `sin > surplus`.

## 3c. Send, claim and refund

1. The sender's account obtains the recipient's deposit facet. `Account.depositFacet` is
   public on purpose: a facet can only deposit, so sharing it is safe and lets any sender
   address a recipient's purse.
2. `sendTransfer` authenticates the owner, reserves the `opId` in `accountState`, withdraws
   the amount from the sender's purse, resolves `component:transfer-book` through Root and
   calls `TransferBook.send` with the memo and opId. The book measures the payment against
   the declared amount, enforces the book bounds, allocates an id and creates a registered
   `TransferContract` that closes over the payment, the recipient facet, the sender's refund
   facet, the claim hash, the expiry, the memo and the opId. A completed opId replay returns
   the stored `(id, uri)` without moving funds; a pending replay returns
   `(false, "pending", id)`; a refusal removes the reservation.
3. If a stipend is set, the same deploy sends native REV from the sender's deployer vault to
   the recipient's REV address so the recipient can pay claim phlo. It is non-refundable and
   capped by book params.
4. The recipient claims by revealing the secret preimage. `TransferContract.claim` checks
   expiry and `ClaimCode.hash(secret) == secretHash`, deposits the payment into the recipient
   facet and re-posts a terminal `claimed` status.
5. After expiry, only the sender's `deployerId` can `refund`; the payment returns to the
   sender's facet and the terminal status is `refunded`.
6. A wrong secret or a foreign refund leaves the cell `open`. A terminal transfer consumes
   the cell and re-posts the terminal status, so a later call replies `closed` instead of
   stalling. Claim and refund race on the same cell; exactly one wins.

## 3d. Repay, savings, and PSM

Repay is the yield source and the solvency repair path:

1. `VaultBook.repay` accrues, measures the payment and computes
   `interestPaid = min(amount, accrued − debt)` and `principalPaid = amount − interestPaid`.
2. `Stablecoin.settle` burns `principalPaid` and deposits `interestPaid` into
   `SurplusBuffer`. Supply falls only by principal; `totalAccruedInterest` falls by
   `interestPaid`.
3. In the same deploy, `SurplusBuffer.cover(0)` cancels outstanding `sin` against the new
   surplus (burning the cancelled stablecoin), then `SurplusBuffer.paySavings` moves
   `floor(surplus · savingsShareBps / 10000)` into `SavingsPool.notify`. If the pool has no
   shares, the notify is skipped and the interest stays in the buffer.
4. `SavingsPool` credits shares by REV address; `notify` raises `totalAssets` without
   minting shares, so the share value rises for existing savers.

PSM creation and use:

1. The system deploy creates the PSM REV purse and stablecoin purse and passes the PSM its
   mint/burn caps; no other contract holds those caps.
2. `fundRev` is permissionless and adds REV to the reserve.
3. `buyStable` mints at par minus the fee and increases signed `stableDebt`; the ceiling
   caps positive debt.
4. `sellStable` burns stablecoin and pays REV at par minus the fee, decreasing `stableDebt`.
   It may drive `stableDebt` negative: that is par redemption of vault-issued stablecoin and
   is required for the peg. An empty REV purse refuses `"buffer"`.
5. `schedulePolicy`/`applyPolicy` change the fee and ceiling only after the timelock.

## 4. Market activation

Activation is the one operation that composes several components. It is deliberately
evidence-first:

1. `MarketIndex` peeks the draft record; check `status == draft`, `stageNonce` and
   `termsHash`.
2. `CurrencyRegistry` returns both currency records; both must be `active`.
3. `OracleRegistry` returns both feed entries; `OracleHub.getPair(base, quote,
   maxPairAgeBlocks)` must report fresh per feed and within the term's age bound.
4. `CurrencyRegistry`/`OracleRegistry` policy hashes must match the terms.
5. `FxPool.attest` returns the immutable `{marketId, termsHash, rb, rq, totalShares, seeded}`;
   `LiquidityLock.info` returns `{funded, released, cancelled, shares, untilHeight}`.
   The pool must be seeded with `rb >= seedBase`, `rq >= max(seedQuote, depthFloorQuote)`
   and `totalShares >= seedInitialShares`; the lock must be funded, unreleased and have
   `untilHeight >= lockUntilHeight`.
6. `MarketDirectory.seal(marketId, termsHash, stageNonce, sponsorSig)` is one cell commit;
   it refuses a missing or mismatched slot.
7. `MarketIndex.activate` consumes `marketState`, rechecks `draft`, `stageNonce` and
   `termsHash`, sets `active` and `byPair[pairKey] = marketId`, posts and replies. If the
   recheck fails after the seal, `fail()` reverts the seal.

No `marketState` cell is held while an external component is awaited. The activation
decision is a snapshot; the `active` transition is the linearization point.

## 5. Trading status

`MarketIndex.status(marketId)` is the single authority for whether a market may trade.
`FxPool.quote`, `swap` and `addLiquidity` read it before consuming state and also call the
pure `TradabilityGate`. There is no separate pool pause flag. `pause`/`delist` is one
`MarketIndex` write; it does not require coordinated unit writes. Claim, refund,
`removeLiquidity` and `LiquidityLock.release` remain available after pause/delist; exits are
never trapped. The full action × state matrix is `docs/SPEC.md` §13.2.

## 6. Rotation and freeze

| Unit class | Lifecycle |
|---|---|
| Stateless (`Clock`, `Verifier`, `Codec`, `Bounds`, `AdminGuard`, maths, views, clients) | `Root.rotate` before freeze; consumers resolve the next version |
| `OracleFeed` | new feed URI and registry version; old feed readable until retired |
| `MarketDirectory` slots | draft overwrite by the factory; sealed at activation; no post-activation overwrite |
| `CurrencyRegistry`, `MarketIndex`, `MarketTerms` | append-only or content-addressed; no destructive rotation |
| Custody (`Stablecoin`, `VaultBook`, `FxPool`, `TransferBook`, `LiquidityLock`, `AccountFactory`) | no in-place rotation; freeze/drain, deploy a new version, re-seed |
| `Root` | immutable after freeze; a successor `Root` is the upgrade path |

## 7. Persistence gate

The `03_accounts` failure class is not detectable by a lexical check alone. The installer
therefore performs an empirical gate after every deploy that creates a bundled contract:

1. deploy the component;
2. wait for the block containing it;
3. call a read arm in a second deploy;
4. restart the node or cross another block;
5. call the read arm again.

A `decode continuation failed`, a missing reply, or a changed result fails the install.
The unit and scenario runs also check that no state cell stores a capability obtained from
`Root.resolve`, `StablecoinDirectory`, `OracleRegistry`, `MarketDirectory`,
`CurrencyRegistry` or `rho:registry:lookup`.

## 8. Migration from v0.2

v0.2 is not patched in place: installed Rholang is immutable. The v0.3 installer deploys a
fresh `Root` and a fresh component set. v0.1/v0.2 remain claimable/refundable until their
cells are drained; no new writes are routed to them after the client manifest switches.
The client, SDK and UI migration is a separate plan.
