# 20 — Invariants and enforcement

Every invariant below has exactly one owner. A second authoritative copy is a defect. The
"Test" column names the obligation; `unit` means the isolated component harness, `scenario`
means a devnet scenario, `TLA+` names the model in `spec/tla`.

## 1. Invariant table

| ID | Invariant | Owner | Enforcement | Test |
|---|---|---|---|---|
| I1 | Quiescent linearity: one `Full` in every cell | every stateful component | every consumed path re-posts; P1/P6 | TLA+ `CellLinearity`, unit |
| I2 | Currency code unique; zone URI matches `ZoneDirectory`; params hash matches the `ZoneFactory` attestation | `CurrencyRegistry` | single-cell commit after reading the directory and verifying the attestation | unit, scenario |
| I3 | One active market per pair; version strictly increases | `MarketIndex` | `stage`/`activate` consume one cell; `byPair` in the same cell | TLA+ `PoolConservation` peer, scenario |
| I4 | Legal market transitions: `draft → active → paused/active → delisted`, `draft → cancelled`; terminal states do not revive | `MarketIndex` | transition table in the arm | unit, scenario |
| I5 | Terms integrity: `termsHash = H(schema, values)`; no mutation | `MarketTerms` | content-addressed `put` recomputes the hash | unit, vectors |
| I6 | Market URI slots are factory-created, sponsor-authorized and sealed before activation | `MarketDirectory` | `bind`/`seal` in one cell; only `MarketFactory` | unit, scenario |
| I7 | Feed freshness: quorum signed prices, median > 0, age, band, spread | `OracleFeed` | one cell per feed; P1 commit after signature verification | TLA+ `CapabilityProvenance` sibling, unit |
| I8 | Three distinct reporter keys; sponsor occupies at most one slot | `OracleRegistry` | registration checks before the registry consume | unit, scenario |
| I9 | Pair rate is fresh per feed and within the caller's age bound | `OracleHub` + caller | `getPair` returns ages; `FxPool`/`CurrencyZone` enforce their term | unit, scenario |
| I10 | Pool reserves equal native custody | `FxPool` | reserves change only with native deposit/withdraw; `attest` reads the purses | TLA+ `PoolConservation`, unit |
| I11 | `totalShares = lpMinted − lpBurned` | `FxPool` | share update and LP mint/burn in one transition | TLA+ `PoolConservation`, unit |
| I12 | Depth floor, min ticket, max trade and first-deposit tolerance | `FxPool` | gate inside the consumed-state critical section; tolerance from params | unit, scenario |
| I13 | Lock is one-shot; release only to beneficiary after height; cancel only by admin | `LiquidityLock` | one cell; consume-first funding; P4 | unit, scenario |
| I14 | Transfer status changes at most once; `open → claimed` xor `open → refunded` | `TransferContract` | one per-transfer cell consume | TLA+ `TransferExclusivity`, unit |
| I15 | No payment is stranded on a refusal | `TransferBook`, `TransferContract`, `FxPool`, `CurrencyZone` | P3/P6: `fail()` after value movement; no `(false, …)` after a write | unit, fault injection |
| I16 | Vault health, ceiling, min/max debt, close factor | `CurrencyZone` | inside the `zoneState` consume, with `RiskMath` before the consume | unit, scenario |
| I17 | `totalDebt = Σ vault.debt` and `totalDebt + badDebt = totalPrincipal + totalAccruedInterest` | `CurrencyZone` | accrual delta applied to vault and totals on every touch; write-off moves residual to `badDebt` | TLA+ `CdpAccounting`, unit |
| I18 | `ertpSupply(stable) = totalPrincipal` | `CurrencyZone` | mint/burn only in zone arms; issuer stays private | TLA+ `CdpAccounting`, unit |
| I19 | Admin threshold and monotone nonce | `Governor` | `authorize` checks threshold and per-domain nonce | TLA+ `AdminNonce`, unit |
| I20 | Capability provenance and bundleability | every component | `check_captures.py`; block-boundary persistence test | TLA+ `CapabilityProvenance`, scenario |
| I21 | Only the owner's `deployerId` passes owner arms; proof never returned after creation; auth tokens are one-shot | `AccountGate`, `AccountFactory` | `AccountGate.verify`; `proofHash`; token cell consume | unit, scenario |
| I22 | Deploy resource bounds | every deploy | `measure_contracts.py`, `check_arch.py`, devnet parse gate | CI |

## 2. Corrected CDP accounting

The v0.2 equation `supply = totalDebt` is false once interest accrues: borrow mints
principal, while interest is a claim on collateral, not new stablecoins. The v0.3 state is

```
totalPrincipal          stablecoins minted minus burned
totalAccruedInterest    interest ever accrued on outstanding debt
totalDebt               Σ vault.debt
badDebt                 debt written off after an under-collateralised liquidation
```

The invariants are

```
ertpSupply(stable) = totalPrincipal
totalDebt = Σ vault.debt
totalDebt + badDebt = totalPrincipal + totalAccruedInterest
```

Every arm that touches a vault first computes the accrual delta with `RiskMath.accrue` and
adds it to both the vault's debt and the totals. A liquidation that seizes less than the
debt writes off the residual:

```
vault.debt       := 0
totalDebt        := totalDebt - residual
badDebt          := badDebt + residual
```

The third equation is preserved because `totalDebt + badDebt` is unchanged. A repayment
reduces `totalPrincipal` by the principal burned and `totalAccruedInterest` by the interest
paid; the sum `totalDebt + badDebt` falls by the payment. `minDebt` is enforced after every
borrow, collateral withdrawal and partial repay: a vault's debt is either zero or at least
`minDebt`.

## 3. Canonical groups (v3)

The v3 encoding is unambiguous: each value is length-prefixed before the `|` join.

```
encode(schema, values) =
  schema ++ "|" ++ join("|", [ len(v).toString() ++ ":" ++ v for v in values ])
hash = blake2b256(utf8(encode(schema, values)))
```

A value containing `|` or `:` cannot collide with another tuple because its length is part
of the encoding. `MarketTerms.put` recomputes this hash and rejects a mismatch.

### Market terms — `rcash:market-terms:v3` (27 values)

| # | Field | Enforced by |
|---|---|---|
| 0 | marketId | `MarketIndex.stage` recomputes `pairKey:vN` |
| 1 | slug | `MarketIndex.stage` uniqueness |
| 2 | base | `MarketIndex.stage`; pair key |
| 3 | quote | `MarketIndex.stage`; pair key |
| 4 | version | `MarketIndex.stage` monotonicity |
| 5 | sponsorPubKey | sponsor signature |
| 6 | sponsorOwnerId | `revAddress` derivation |
| 7 | baseZoneUri | `CurrencyRegistry` |
| 8 | quoteZoneUri | `CurrencyRegistry` |
| 9 | baseFeedPolicyHash | `OracleRegistry` live policy |
| 10 | quoteFeedPolicyHash | `OracleRegistry` live policy |
| 11 | baseSpreadBps | `FxPool` fee formula |
| 12 | skewSpreadBps | `FxPool` fee formula |
| 13 | maxTradeBps | `FxPool` max input |
| 14 | minLiquidity | first deposit / share floor |
| 15 | firstDepositToleranceBps | `FxPool` first deposit (replaces the hardcoded 1%) |
| 16 | depthFloorQuote | `FxPool` gate and activation |
| 17 | minTicketQuote | `FxPool` gate |
| 18 | seedBase | `FxPool` constructor and `sealSeed` |
| 19 | seedQuote | `FxPool` constructor and `sealSeed` |
| 20 | seedInitialShares | `FxPool` constructor, lock and activation |
| 21 | lockBeneficiaryPubKey | `LiquidityLock` constructor |
| 22 | lockMinBlocks | `MarketIndex.stage` (`now + lockMinBlocks <= lockUntilHeight`) |
| 23 | lockUntilHeight | `LiquidityLock` and activation |
| 24 | bookDefaultExpiryBlocks | `TransferBook.send` default |
| 25 | bookMaxExpiryBlocks | `TransferBook.send` maximum |
| 26 | maxPairAgeBlocks | `FxPool`/`CurrencyZone` caller bound to `OracleHub.getPair` |

Removed from the v1 schema: `depthFloorUsdE8`, `minTicketUsdE8`, `protocolFeeBps`,
`autoPause`. They were hashed but not enforced. A field is either enforced on-chain or
absent. A price-skew field is also absent: there is no third reference against which to
measure skew.

### Zone params — `rcash:zone-params:v3` (8 values)

`currency, mcrBps, bonusBps, closeFactorBps, ratePerBlock, debtCeiling, minDebt, maxDebt`.
Bounds are checked by `Bounds.checkZone` before `CurrencyRegistry.register` and at zone
construction. Zone params are immutable for the life of the zone.

### Feed policy — `rcash:oracle-policy:v3` (12 values)

`currency, k0, k1, k2, sponsor, quorum, maxAgeBlocks, maxSpreadBps, minPrice, maxPrice,
trialBlocks, trialMinSubmits`. `Bounds.checkFeed` enforces distinct keys, the sponsor slot
rule, `quorum` within 1..3, `trialMinSubmits >= quorum`, and the age/spread/band ranges.

### Book params — `rcash:book-params:v3` (4 values)

`marketId, defaultExpiryBlocks, maxExpiryBlocks, minAmount`. `TransferBook.send` enforces
the expiry range and the minimum amount; `defaultExpiryBlocks` is the default when the
caller passes zero.

## 4. Defect closure map

| v0.2 defect | Closure in v0.3 |
|---|---|
| `TransferBookV2.send` peek then write after the pool await | P3 effect-then-commit; per-transfer cells; `fail()` if status changed |
| `ListingRegistry` eight maps in one cell | `CurrencyRegistry`, `MarketTerms`, `MarketIndex`, `MarketDirectory`, `ListingViews` |
| `registerMarketCap` stores caller-supplied caps | deleted; factory-created URIs in `MarketDirectory`, sealed before activation |
| `minDebt` never enforced | `CurrencyZone` borrow, collateral withdrawal and partial repay |
| hardcoded 1% first deposit | `firstDepositToleranceBps` (field 15) |
| economic bounds only in Rust | `Bounds.check*` on-chain in registration, stage and construction |
| `protocolFeeBps`, `autoPause` unenforced | removed from the v3 schema |
| dead `bounds`, `tombstone`, `keyUse` | deleted; `Bounds` is a pure component; status replaces tombstone |
| live cap in a bundle (`03_accounts`) | `Root` URI strings only; no registry-resolved cap in a bundle |
| `totalDebt` drifts from `Σ debt` | accrual delta applied to totals on every touch |
| liquidation on a stale price | `liquidate` requires a fresh pair read |
| activation can overwrite a cancel | consume + revalidate status/nonce/terms; `fail()` on mismatch |
| `borrow` awaits a caller `depositFacet` after mint | deleted; the zone returns the payment |
| permissionless `lockTerms` | deleted; terms are a constructor argument |
| permissionless `ComponentRegistry.lock`/`set` | deleted; `Root` is installer-signed and freezes terminally |
| `LiquidityLock.lock` peek/deposit/consume race | consume-first funding; P4; `fail()` on native refusal |
| zone view leaks the vault auth | views return `{ownerId, collateral, debt, lastHeight, health}` only |
| feed policy signature can bind a fake feed | signed `feedId` + `feed.attest()` comparison |
| `getPair` claims per-market skew it cannot see | caller passes `maxAgeBlocks`; skew field removed |

## 5. Stable refusal strings

Refusals are part of the interface. Tests assert the exact string.

```
not owner                 no account              unknown asset
unknown market            no market               market not active
paused                    paused feed             stale feed
trial                     quorum                  spread
band                      below depth             below min ticket
max trade                 slippage                too many shares
not enough shares         first deposit           reserve mismatch
seed mismatch             shares mismatch         unfunded lock
lock mismatch             lock too short          terms drift
pair mismatch             pair has active market  not draft
not sealed                not beneficiary         too early
not open                  expired                 not expired
bad secret                close                   healthy
below MCR                 overpayment             min debt
max debt                  ceiling                 height not monotonic
bad signature             bad sponsor signature   currency not authorized
currency exists           zone currency mismatch  params hash mismatch
zone not registered       duplicate              unknown component
frozen                    replay                  below threshold
expiry                    expiry too long          amount too small
```
