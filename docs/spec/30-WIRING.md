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
| `CurrencyRegistry` (signed system deploy) | `StablecoinDirectory` | `currency → {stablecoinUri, custodyUri, paramsUri, vaultUri, liquidationUri, paramsHash, sponsor, status}` |
| `MarketFactory` | `MarketDirectory` | `marketId → {poolUri, bookUri, lockUri, termsHash}` |

There is no separate stablecoin factory in v0.4: `31_stablecoin.rho` verifies the sponsor
signature, bounds and params hash before creating the system, so the deploy is the creation
gate. `CurrencyRegistry` verifies the live attestation and writes the directory; the
directory's only write capability is in the registry's closure.

`OracleFeed` is deployed per currency by its sponsor; `OracleRegistry.registerFeed` binds
the URI after the sponsor signature and feed attestation check. There is no feed factory.

The factory is the only writer. A caller cannot supply a pool, book, lock, stablecoin or feed.
The sponsor signs the economic terms, not an arbitrary contract URI. `MarketDirectory`
accepts draft binds and a final `seal`; a sealed slot is immutable for that market version.

`Governor` owns the admin set, threshold and per-domain nonce. A unit that has an admin arm
calls `Governor.authorize(domain, nonce, action, argsHash, sigs)`, receives the verified
intent, and applies it locally. The governor's nonce is the replay ledger; an action that
fails after authorization is lost, which is a liveness cost, not a safety defect.

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
| 10d | `MarketTerms`, `MarketIndex`, `MarketDirectory`, `MarketFactory` | `component:market-*` |
| 11 | `AccountFactory` (creates `Account`, `PurseStore`, `AccountGate` per owner) | `component:account-factory` |
| 12 | per currency: deploy `31_stablecoin` with signed params, then `CurrencyRegistry.register` with the sponsor signature | `currency:<CODE>` |
| 12 | per currency: `OracleFeed`, then `OracleRegistry.registerFeed` | `feed:<CODE>` |
| 13 | per market: `MarketFactory.createMarket`, seed, lock, activate | `market:<PAIR>:vN` |
| 14 | `TransferClient`, `ListingViews` | `component:transfer-client`, `component:listing-views` |
| 99 | `Root.freeze` | — |

The installer writes `deployments/devnet-v4.json` only after the final step. Each step
records the deploy id, block hash, block number, URIs, measured bytes/depth and phlo. A
failed step aborts the install; it never writes a half-installed manifest.

## 3b. Currency listing and liquidation

Listing is evidence-first and idempotent per code:

1. The sponsor deploys `31_stablecoin` with the canonical params, hash and signature; the
   deploy refuses a bad signature, out-of-bounds params, a hash mismatch or a duplicate
   system for the code (the registry check below is the authoritative duplicate gate).
2. `CurrencyRegistry.register(code, scUri, custodyUri, paramsUri, vaultUri, liqUri,
   paramsHash, sponsor, sig)` verifies `rcash:currency-register:v1|code|scUri|paramsHash|sponsor`,
   calls the live `Stablecoin.attest`, and requires the currency, params hash and sponsor to
   match. It then writes `StablecoinDirectory` and the currency record in one commit.
3. A duplicate code is refused before the signature check; a bad signature is refused before
   the directory write. `setPaused` is governor-gated per domain `currency-registry`.

Liquidation is permissionless but capability-bound:

1. A liquidator takes a stablecoin payment and calls `LiquidationEngine.liquidate(ownerId,
   payment, minCollateral)`.
2. The VaultBook accrues interest, rejects a healthy vault, bounds the repayment by
   `ceil(debt · closeFactorBps / 10000)` and computes the seizure with `CollateralMath.payout`.
3. If the vault cannot cover the bonus slice, clearing is allowed only when the repayment
   covers the collateral's value; the residual is booked to `badDebt` and the vault debt is
   cleared.
4. The burn and custody withdrawal happen before the single vault/totals commit. Any refusal
   aborts the deploy, so a half-settled liquidation cannot persist. Refusals before the
   consume return the payment to the caller.

## 3c. Send, claim and refund

1. The sender's account obtains the recipient's deposit facet. `Account.depositFacet` is
   public on purpose: a facet can only deposit, so sharing it is safe and lets any sender
   address a recipient's purse.
2. `sendTransfer` authenticates the owner, withdraws the amount from the sender's purse,
   resolves `component:transfer-book` through Root and calls `TransferBook.send`. The book
   allocates an id and creates a registered `TransferContract` that closes over the payment,
   the recipient facet, the sender's refund facet, the claim hash and the expiry.
3. The recipient claims by revealing the secret preimage. `TransferContract.claim` checks
   `ClaimCode.hash(secret) == secretHash`, deposits the payment into the recipient facet and
   re-posts a terminal `claimed` status.
4. After expiry, only the sender's `deployerId` can `refund`; the payment returns to the
   sender's facet and the terminal status is `refunded`.
5. A wrong secret or a foreign refund leaves the cell `open`. A terminal transfer consumes
   the cell and re-posts the terminal status, so a later call replies `closed` instead of
   stalling. Claim and refund race on the same cell; exactly one wins.

## 4. Market activation

Activation is the one operation that composes several components. It is deliberately
evidence-first:

1. `MarketIndex` peeks the draft record; check `status == draft`, `stageNonce` and
   `termsHash`.
2. `CurrencyRegistry` returns both currency records; both must be `active`.
3. `OracleRegistry` returns both feed entries; `OracleHub.getPair(base, quote,
   maxPairAgeBlocks)` must report fresh per feed and within the term's age bound.
4. `CurrencyRegistry`/`OracleRegistry` policy hashes must match the terms.
5. `FxPool.attest` returns the immutable `{marketId, termsHash, seedBase, seedQuote,
   initialShares, seeded}`; `LiquidityLock.attest` returns `{funded, released, cancelled,
   shares, untilHeight}`; `TransferBook.attest` returns `{marketId, termsHash, active}`.
   The seed must equal the terms, the lock must be funded and unreleased, and shares must
   equal `initialShares`.
6. `MarketDirectory.seal(marketId, termsHash, stageNonce, sponsorSig)` is one cell commit;
   it refuses a missing or mismatched slot.
7. `MarketIndex.activate` consumes `marketState`, rechecks `draft`, `stageNonce` and
   `termsHash`, sets `active` and `byPair[pairKey] = marketId`, posts and replies. If the
   recheck fails after the seal, `fail()` reverts the seal.

No `marketState` cell is held while an external component is awaited. The activation
decision is a snapshot; the `active` transition is the linearization point.

## 5. Trading status

`MarketIndex.status(marketId)` is the single authority for whether a market may trade.
`FxPool.swap`/`addLiquidity` and `TransferBook.send` read it before consuming state. Local
`paused` flags may only reduce trading. `pause`/`delist` is one `MarketIndex` write; it does
not require three coordinated unit writes. Claim, refund and release remain available after pause/delist.

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
