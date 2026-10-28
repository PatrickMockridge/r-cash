# 20 — Invariants and enforcement

Every invariant below has exactly one owner. A second authoritative copy is a defect. The
"Test" column names the obligation; `unit` means the isolated component harness, `scenario`
means a devnet scenario, `TLA+` names the model in `spec/tla`.

## 1. Invariant table

| ID | Invariant | Owner | Enforcement | Test |
|---|---|---|---|---|
| I1 | Quiescent linearity: one `Full` in every cell | every stateful component | every consumed path re-posts; P1/P6 | TLA+ `CellLinearity`, unit |
| I2 | Currency code unique; stablecoin URI, params hash and sponsor match the live attestation; the directory is written only after that check | `CurrencyRegistry`, `StablecoinDirectory` | one registry consume at commit; the registry holds the directory's only write capability | unit, scenario |
| I3 | One active-or-paused market per **unordered** pair; both orientation keys resolve to it; version strictly increases | `MarketIndex` | `stage`/`activate` consume one cell; `byPair` writes both orientations; the reverse stage is refused | TLA+ `PoolConservation` peer, scenario |
| I4 | Legal market transitions: `draft → active → paused/active → delisted`; a delisted version may be replaced only by a higher version | `MarketIndex` | governor-gated `setStatus`; `stage` checks pair status and version | unit, scenario |
| I5 | Terms integrity: `termsHash = H(schema, values)`; no mutation | `MarketTerms` | content-addressed `put` recomputes the hash | unit, vectors |
| I6 | Market URI slots are factory-created, sponsor-authorized and sealed before activation | `MarketDirectory` | `bind`/`seal` in one cell; only `MarketFactory` | unit, scenario |
| I7 | Feed freshness: quorum signed prices, median > 0, age, band, spread | `OracleFeed` | one cell per feed; P1 commit after signature verification | TLA+ `CapabilityProvenance` sibling, unit |
| I8 | Three distinct reporter keys; sponsor occupies at most one slot | `OracleRegistry` | registration checks before the registry consume | unit, scenario |
| I9 | Pair rate is fresh per feed and within the caller's age bound | `OracleHub` + caller | `getPair` returns ages; `FxPool` enforces its term | unit, scenario |
| I10 | Pool reserves equal native custody | `FxPool` | reserves change only with native deposit/withdraw; `attest` reads the purses | TLA+ `PoolConservation`, unit |
| I11 | `totalShares = lpMinted − lpBurned` | `FxPool` | share update and LP mint/burn in one transition | TLA+ `PoolConservation`, unit |
| I12 | Depth floor, min ticket, max trade and first-deposit tolerance | `FxPool` | gate inside the consumed-state critical section; tolerance from params | unit, scenario |
| I13 | The seed lock is one-shot; only the beneficiary may release after the height; a released or cancelled lock refuses with `closed`; cancel is governor-gated | `LiquidityLock` | one cell consumed by fund and release/cancel; the terminal flags are re-posted | unit, scenario |
| I14 | Transfer status changes at most once; `open → claimed` xor `open → refunded`; a terminal transfer keeps a quiescent cell and refuses with `closed` | `TransferContract` | one per-transfer cell consume; the terminal state is re-posted after the deposit | TLA+ `TransferExclusivity`, unit |
| I15 | No payment is stranded on a refusal | `TransferBook`, `TransferContract`, `FxPool` | P3/P6: `fail()` after value movement; no `(false, …)` after a write | unit, fault injection |
| I19 | Admin threshold and monotone nonce | `Governor` | `authorize` checks threshold and per-domain nonce | TLA+ `AdminNonce`, unit |
| I20 | Capability provenance and bundleability | every component | `check_captures.py`; block-boundary persistence test | TLA+ `CapabilityProvenance`, scenario |
| I21 | Only the owner's `deployerId` passes owner arms; proof never returned after creation; auth tokens are one-shot | `AccountGate`, `AccountFactory` | `AccountGate.verify`; `proofHash`; token cell consume | unit, scenario |
| I22 | Deploy resource bounds | every deploy | `measure_contracts.py`, `check_arch.py`, devnet parse gate | CI |
| I23 | An external asset is listed only with a sponsor signature, an adapter attestation, `kind: external` and `decimals: 8`; it has no R-Cash issuer system | `CurrencyRegistry`, `AssetResolver` | `registerExternal` verifies before the one cell commit; `AssetResolver` branches on kind | unit, scenario |
| I24 | Mesh discovery: every supported pair is listed in the client config with `active`, `draft` or `unlisted`; only priority pairs are created and seeded at launch | `configs/mesh.json`, `ListingViews`, web | config validation in `tools/mesh.py`; `ListingViews.markets` plus the config matrix | unit, web |

I16–I18 are intentionally retired: they were removed with the old lending
section and have no normative statement. The current catalogue is I1–I15 and
I19–I24. `check_traceability.py` requires every listed invariant to have this
text and a check; a gap is an error.

## 2. Stablecoin issuer (v0.4)

The issuer is DAI-like with REV-only collateral and separate contracts per authority. The
old CDP accounting section is deleted; these are the issuer's invariants.

| ID | Invariant | Owner | Enforcement | Test |
|---|---|---|---|---|
| S1 | `supply = totalPrincipal = minted − burned`; `supply ≤ maxSupply`; only the VaultBook/Engine hold the scoped mint/burn caps | `Stablecoin` | one `issuerState` cell; cap comparison before the ERTP mint/burn; P3 commit | unit |
| S2 | `totalDebt = Σ vault.debt` and `totalCollateral = Σ vault.collateral` | `VaultBook` | every arm writes the vault and all totals through one `vaultUpdate` commit | unit |
| S3 | `totalDebt + sin + psmDebt = supply + totalAccruedInterest`; `totalAccruedInterest` is net unsettled interest, `sin` is outstanding bad debt net of surplus, `psmDebt` is signed, and `badDebt` is a cumulative memo outside the identity | `VaultBook` + `Stablecoin` + `SurplusBuffer` + `PegStabilityModule` | the same commit carries the debt, interest, bad-debt, supply and PSM deltas; no second principal ledger | unit, scenario |
| S4 | Mint and collateral withdrawal preserve `health(collateral, debt, rate, mcr)`; mint also enforces min/max debt and the ceiling | `VaultBook` | `CollateralMath.health` before the commit; stale feed or missing rate is a refusal | unit |
| S5 | Only an unhealthy vault is liquidatable, bounded by the close factor, and only through the liquidation capability | `VaultBook`, `LiquidationEngine` | the engine holds the only `liquidationAuth`; the arm checks health and `ceil(debt·closeFactor)` | unit, scenario |
| S6 | A liquidation seizes `payout(repay, bonus, rate)` or, when the vault cannot cover that slice, all collateral only if the repayment covers the collateral's value; the uncovered residual is booked to `badDebt` (memo) and `sin` (outstanding), and the debt cleared. The write-off calls `SurplusBuffer.cover` in the same deploy, which burns `min(surplus, sin)` | `VaultBook`, `SurplusBuffer` | effect-then-commit: burn, custody withdraw, cover, then one vault/totals write; a `rev` mismatch fails the deploy | unit, scenario |
| S7 | REV leaves custody only through the custody capability; stablecoin leaves supply only through burn; repay splits principal and interest through `Stablecoin.settle`, so supply falls only by principal and interest is deposited to the buffer; a refusal on `liquidate` returns the payment | `CollateralCustody`, `Stablecoin`, `VaultBook` | scoped caps in closure; `settle` burns principal and deposits interest; the liquidate arm peeks the amount and returns `(false, reason, payment)` before any consume | unit |
| S8 | One system per currency; listing requires the sponsor signature and the live attestation | `CurrencyRegistry` | registry consume at commit; directory write with a registry-only capability | unit, scenario |
| S9 | Buffer waterfall: interest is deposited into `SurplusBuffer`, `cover(0)` cancels outstanding `sin` against surplus, and `paySavings` then moves `floor(surplus·savingsShareBps/10000)`; solvency precedes yield and no stablecoin is counted twice | `VaultBook`, `SurplusBuffer` | one deploy, in that order; each step consumes and reposts its own cell with `rev` | unit, scenario |
| S10 | Savings conservation: `totalShares = Σ shares[ownerId]`; deposits and withdrawals move assets and shares together at floored pro-rata value; `notify` raises assets without minting shares; no public donation arm exists | `SavingsPool` | one `savingsState` cell; prepare/commit with `rev`; zero-share deposit refused | unit, scenario |
| S11 | PSM conservation: `stableDebt` is signed, each buy adds exactly the minted `stableOut` to supply and debt, each sell burns exactly `stableIn` and subtracts it from debt and supply; fees stay in the REV purse | `PegStabilityModule` | the burn/mint and debt write are exercised before the cell commit; a refusal returns the payment | unit, scenario |
| S12 | Governed parameter changes: risk params, savings share and PSM policy are scheduled, execute only after the timelock, recheck the args hash and apply to subsequent arms; emergency pause and market status remain immediate | `Governor`, `RiskParameters`, `SurplusBuffer`, `PegStabilityModule` | `schedule`/`execute` in one governor cell; each apply validates through `Bounds` and commits its own cell | unit, scenario |

## 3. Canonical groups (v3)

The v3 encoding is unambiguous: each value is length-prefixed before the `|` join.

```
encode(schema, values) =
  schema ++ "|" ++ join("|", [ len(v).toString() ++ ":" ++ v for v in values ])
hash = blake2b256(utf8(encode(schema, values)))
```

A value containing `|` or `:` cannot collide with another tuple because its length is part
of the encoding. `MarketTerms.put` recomputes this hash and rejects a mismatch.

### Market terms — `rcash:market-terms:v4`

The v0.4 schema drops the old zone URIs; it is the active 25-value schema. The terms
store is keyed by the Codec canonical string of these values, and the sponsor signs
`rcash:market-create:v1|marketId|canonical|sponsor`.

| # | Field | Enforced by |
|---|---|---|
| 0 | marketId | `MarketIndex.stage`; directory and index keys |
| 1 | slug | `MarketIndex.stage` uniqueness |
| 2 | base | `MarketIndex.stage`; pair key |
| 3 | quote | `MarketIndex.stage`; pair key |
| 4 | version | `MarketIndex.stage` monotonicity after a delisted version |
| 5 | sponsorPubKey | sponsor signature and terms match |
| 6 | sponsorOwnerId | sponsor record |
| 7 | baseFeedPolicyHash | `MarketFactory` live `OracleRegistry` policy |
| 8 | quoteFeedPolicyHash | `MarketFactory` live `OracleRegistry` policy |
| 9 | baseSpreadBps | `FxPool` fee formula |
| 10 | skewSpreadBps | `FxPool` fee formula |
| 11 | maxTradeBps | `FxPool` max input |
| 12 | minLiquidity | `FxPool` first deposit floor |
| 13 | firstDepositToleranceBps | `FxPool` first deposit balance |
| 14 | depthFloorQuote | `MarketIndex.activate` |
| 15 | minTicketQuote | `FxPool` swap gate |
| 16 | seedBase | `MarketIndex.activate` live `rb` lower bound |
| 17 | seedQuote | `MarketIndex.activate` live `rq` lower bound |
| 18 | seedInitialShares | `MarketIndex.activate` live `totalShares` lower bound |
| 19 | lockBeneficiaryPubKey | `MarketFactory` equality with `sponsorPubKey`; `LiquidityLock` beneficiary |
| 20 | lockMinBlocks | `LiquidityLock.fund` (`untilHeight >= now + lockMinBlocks`) and factory minimum |
| 21 | lockUntilHeight | `MarketIndex.activate` compares against `LiquidityLock.info` |
| 22 | bookDefaultExpiryBlocks | `Bounds.checkTerms` against the global book params |
| 23 | bookMaxExpiryBlocks | `Bounds.checkTerms` against the global book params |
| 24 | maxPairAgeBlocks | `FxPool` bound passed to `OracleHub.getPair` |

Removed from the v1 schema: `depthFloorUsdE8`, `minTicketUsdE8`, `protocolFeeBps`,
`autoPause`. They were hashed but not enforced. A field is either enforced on-chain or
absent. A price-skew field is also absent: there is no third reference against which to
measure skew.

### Feed policy — `rcash:oracle-policy:v3` (12 values)

`currency, k0, k1, k2, sponsor, quorum, maxAgeBlocks, maxSpreadBps, minPrice, maxPrice,
trialBlocks, trialMinSubmits`. `Bounds.checkFeed` enforces distinct keys, the sponsor slot
rule, `quorum` within 1..3, `trialMinSubmits >= quorum`, and the age/spread/band ranges.

### Book params — `rcash:book-params:v4` (6 values)

`defaultExpiryBlocks, maxExpiryBlocks, minAmount, maxMemoBytes, maxOpIdBytes, maxStipend`.
`TransferBook.send` enforces the expiry range, the minimum amount, the memo and opId byte
bounds and the stipend cap; `defaultExpiryBlocks` is the default when the caller passes
zero. The book is global (one `component:transfer-book`), so there is no `marketId`.

## 4. Defect closure map

| v0.2 defect | Closure in v0.3 |
|---|---|
| `TransferBookV2.send` peek then write after the pool await | P3 effect-then-commit; per-transfer cells; `fail()` if status changed |
| `ListingRegistry` eight maps in one cell | `CurrencyRegistry`, `MarketTerms`, `MarketIndex`, `MarketDirectory`, `ListingViews` |
| `registerMarketCap` stores caller-supplied caps | deleted; factory-created URIs in `MarketDirectory`, sealed before activation |
| hardcoded 1% first deposit | `firstDepositToleranceBps` (field 15) |
| economic bounds only in Rust | `Bounds.check*` on-chain in registration, stage and construction |
| `protocolFeeBps`, `autoPause` unenforced | removed from the v3 schema |
| dead `bounds`, `tombstone`, `keyUse` | deleted; `Bounds` is a pure component; status replaces tombstone |
| live cap in a bundle (`03_accounts`) | `Root` URI strings only; no registry-resolved cap in a bundle |
| activation can overwrite a cancel | consume + revalidate status/nonce/terms; `fail()` on mismatch |
| permissionless `lockTerms` | deleted; terms are a constructor argument |
| permissionless `ComponentRegistry.lock`/`set` | deleted; `Root` is installer-signed and freezes terminally |
| `LiquidityLock.lock` peek/deposit/consume race | consume-first funding; P4; `fail()` on native refusal |
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
bad secret                height not monotonic
bad signature             bad sponsor signature   currency not authorized
currency exists           params hash mismatch    duplicate
unknown component         frozen                    replay                  below threshold
expiry                    expiry too long          amount too small
```