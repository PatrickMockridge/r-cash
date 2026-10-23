# 10 — Component catalogue

Every component is a separately deployed contract. `R` components are created per instance
at runtime. A factory and its directory may share one deploy term so they can hold each
other's locally created capability; they remain separate contracts with separate state.

The machine-readable form is [`contracts/components.json`](../../contracts/components.json).
The dependency graph in that file is the **call** graph. Factory creation edges are listed
separately and do not create a runtime cycle.

## 1. Kernel and pure helpers

| Component | State | Interface | Responsibility |
|---|---|---|---|
| `Root` | `rootState` | `resolve(key, minVersion)`, `get(key)`, `keys()`, `register(key, uri, version, kind)`, `rotate(key, expectedVersion, newUri, newVersion, sigs)`, `deprecate(key, sigs)`, `freeze(sigs)`, `admin(...)` | Versioned URI directory. Bootstrap writes authenticate the deploy's `deployerId` against `installer`; rotations are admin-signed; `freeze` is terminal. |
| `Clock` | none | `now()` | One block-height source. |
| `Verifier` | none | `hash(bytes)`, `sigOk(digest, sig, pubKey)`, `claimHash(secret)` | One crypto boundary. |
| `Codec` | none | `canonical(schema, values)`, `hash(schema, values)` | Length-prefixed canonical encoding and hashing. |
| `Bounds` | none | `checkZone`, `checkFeed`, `checkPool`, `checkBook`, `checkTerms` | Pure on-chain bounds for every canonical group. |
| `AdminGuard` | none | `verify(domain, nonce, action, argsHash, sigs, admins, threshold)` | Threshold signature verification over `rcash:admin:v1|domain|nonce|action|args`. |
| `AmmMath` | none | `value`, `weight`, `fee`, `out`, `shares` | Pure FPMM arithmetic, floor outputs and shares. |
| `OracleMath` | none | `median3`, `fresh`, `rate` | Median, spread, freshness, cross rate. |
| `ClaimCode` | none | `hash(secret)` | Claim-secret hashing. |

## 2. Authority and discovery

| Component | State | Interface | Responsibility |
|---|---|---|---|
| `Governor` | `governorState` | `authorize(domain, nonce, action, argsHash, sigs)`, `admins()`, `admin(...)` | Owns the admin set, threshold and per-domain nonce. Units call `authorize` and apply the verified intent. `AdminGuard` is its pure verifier. |

`OracleRegistry` and `MarketDirectory`. `Directory` and `ComponentRegistry` are deleted.

## 3. Registries

| Component | State | Interface | Responsibility |
|---|---|---|---|
| `CurrencyRegistry` (planned v0.4) | `currencyState` | `register`, `currency`, `currencies`, `admin` | Currency records. Registration requires the sponsor deployer key, a signature over the stablecoin-system URI and params hash, a `StablecoinDirectory(code)` match and the live stablecoin attestation. Status is `active` or `paused`. |
| `MarketTerms` | `termsState` | `put`, `get`, `boundsOk` | Content-addressed `termsHash → {terms, values}`. `put` recomputes the hash and rejects a mismatch. |
| `MarketIndex` | `marketState` | `stage`, `activate`, `pause`, `delist`, `cancel`, `market`, `marketFor`, `status`, `isActive`, `admin` | Market status, pair uniqueness, version monotonicity and nonce in one cell. |
| `MarketDirectory` | `directoryState` | `bind`, `seal`, `unseal`, `byId`, `slot` | Per-market `{poolUri, bookUri, lockUri, termsHash, sealed}`. Only `MarketFactory` writes; a draft slot may be overwritten, then sealed. |
| `OracleRegistry` | `oracleRegState` | `registerFeed`, `feedEntry`, `reporters`, `allowlist`, `admin` | Reporter allowlist and per-currency feed URI plus policy hash. |

## 4. Domain components

| Component | State | Interface | Responsibility |
|---|---|---|---|
| `OracleFeed` (currency) | `feedState` | `submit`, `get`, `activate`, `info`, `admin` | Per-currency feed deployed by the sponsor and bound by `OracleRegistry`; no factory. |
| `OracleHub` | none | `get`, `feedStatus`, `getPair`, `reporters` | Stateless router; `getPair(base, quote, maxAgeBlocks)` returns per-feed freshness and ages. Callers enforce their own age bound. |
| `MarketFactory` | none | `createMarket(terms, termsValues, sponsorSig)` | Puts terms in `MarketTerms`, creates `FxPool`, `LiquidityLock` and `TransferBook` from templates, binds their URIs in `MarketDirectory`, stages `MarketIndex`. |
| `FxPool` (market) | `poolState` | `quote`, `swap`, `quoteAdd`, `addLiquidity`, `removeLiquidity`, `reserves`, `params`, `pair`, `terms`, `lpAsset`, `sealSeed`, `attest`, `admin` | Reserve and share accounting, swaps, liquidity, seed attestation; holds base/quote/LP purses. |
| `LiquidityLock` (market) | `lockState` | `lock`, `release`, `info`, `attest`, `admin` | One-shot seed custody until a height; beneficiary-only release; admin cancel only. |
| `TransferBook` (market) | `bookState` | `send`, `nextId`, `terms`, `escrows`, `attest`, `admin` | Allocates ids, performs the swap, creates a `TransferContract` per transfer. |
| `TransferContract` (transfer, R) | `transferState` | `claim`, `refund`, `info` | Authoritative transfer object: record, payment and claim token in one cell. |
| `TradabilityGate` | none | `admit(status, fresh, value, inputValue, terms)` | Pure policy verdict; receives all inputs and never calls back into the pool. |
| `AccountFactory` | `factoryState` | `getOrCreate`, `verify`, `accountOf`; `authorize`/`consumeAuth` next | One proof per owner; the proof name is created once and returned only by `getOrCreate`. Account provisioning and one-shot auth tokens arrive with the account layer. |
| `AccountProvisioner` | none | `create(ownerId, pubKeyBytes)` | Orchestrates the three account templates. |
| `Account` (owner, R) | `purseStoreUri`, `transferClientUri` | `deposit`, `withdraw`, `balance`, `depositFacet`, `sendTransfer`, `claimTransfer`, `refundTransfer` | Owner-authenticated thin payment router. Holds the `PurseStore` capability and resolves the transfer client; no vault state or CDP arms. |
| `PurseStore` (owner, R) | `purseState` | `ensure`, `deposit`, `withdraw`, `balance`, `facet` | One purse per asset; ERTP custody. |
| `AccountGate` (owner, R) | none | `verify(deployerId)` | Owner authentication; no state. |
| `TransferClient` | none | `send`, `claim`, `refund`, `info` | Account-side transfer orchestration; resolves the book and market. |
| `AssetResolver` | none | `meta(assetId)`, `issuer(assetId)`, `makePurse(assetId)`, `makeFacet(assetId)` | Derives asset metadata and read-only issuer/purse capabilities from the registries; no second copy of asset truth. |
| `ListingViews` | none | `currency`, `asset`, `assets`, `markets`, `marketView`, `marketFor`, `terms`, `isActive` | Read-only projection of the registries, markets and feeds. |

## 5. Atomic clusters

The following are single contracts because no cross-cell transaction exists. Splitting them
would make the invariant unprovable.

| Cluster | Invariant |
|---|---|
| `FxPool` | reserves, shares, LP mint/burn and seed attestation move together |
| `MarketIndex` | status, pair index, version and nonce move together |
| `MarketDirectory` | the three URI slots and the seal move together |
| `TransferContract` | the transfer record, payment and claim token move together |

`Account` owns only its routing map; purse custody is in `PurseStore`, vault authority is in

## 6. Split map

### `ListingRegistry.rho` (1037 lines / 32 contracts)

| Current region | Destination |
|---|---|
| `listingNow`, `listingPairKey`, `listingZoneOk`, `listingZoneParamsHash` | `Clock`, `Bounds`, `Codec` |
| `stageMarket`, `listingStage`, `listingStoreDraft` | `MarketIndex.stage` + `MarketTerms` + `MarketFactory` |
| `activateMarket`, `listingActivate` | `MarketIndex.activate` + `MarketDirectory.seal` + attestations |
| `registerMarketCap`, `marketCap`, `marketCapsById` | `MarketDirectory`; caller-supplied caps are deleted |
| `asset`, `assets` | `ListingViews` + `AssetResolver` derivation |
| `markets`, `marketView`, `marketFor`, `terms`, `isActive` | `ListingViews` |
| `admin`, `listingAdminApply` | `Governor` |
| `marketViews`, `bounds`, `tombstone` | deleted; views are projections; bounds are `Bounds` |

### `AccountBodyV2.rho` (963 / 26) and `AccountFactoryV2.rho`

| Current region | Destination |
|---|---|
| asset metadata and controller URI resolution | `AssetResolver` |
| internal purse, lookup purse, ensure purse | `PurseStore` |
| book lookup and legacy fallbacks | `TransferClient`; legacy fallback deleted |
| deposit, withdraw, balance, deposit facet | `Account` → `PurseStore` |
| send/claim/refund and `ByMarket` variants | `Account` → `TransferClient` → `TransferBook`/`TransferContract` |
| deployerId checks in every arm | `AccountGate` once per arm |
| bundled account capability in factory state | account capability and `proofHash` stored directly |
| `ListingRegistry`, `Directory`, `Components` captures | deleted; `rootUri` string only |

### `OracleHubV2.rho` (737 / 44)

| Current region | Destination |
|---|---|
| median, max, min, freshness, decision, policy hash | `OracleMath`, `Codec` |
| `openFeed` closure | per-currency `OracleFeed` deploy + `OracleRegistry.registerFeed` |
| per-feed submit/get/status/activate/pause/restart | `OracleFeed` |
| hub submit/get/feedStatus/activateFeed/getPair/reporters | `OracleHub` |
| allowlist, add/remove reporter, admin | `OracleRegistry`, `Governor` |
| `keyUse` | deleted |

### `FxPoolV2.rho` (648 / 21)

| Current region | Destination |
|---|---|
| value, weight, fee, out, input value | `AmmMath` |
| reserves, shares, LP issuer, custody purses, mint/burn | stay in `FxPool` |
| `lockTerms` | deleted; `termsHash` is a constructor argument |
| hardcoded first-deposit tolerance | `firstDepositToleranceBps` from params |
| `poolGate` | `TradabilityGate` plus the pool's own bounds |
| `sealSeed`, `attest` | added; activation reads the attestation |

### `TransferBookV2.rho` (360 / 17)

| Current region | Destination |
|---|---|
| record, status, transfer-id helpers | `TransferContract` per transfer |
| escrow deposit/withdraw | deleted; the per-transfer cell holds the payment |
| send | `TransferBook.send` effect-then-commit |
| claim/refund | `TransferContract.claim/refund` on one cell |
| quote | `TransferClient` or book passthrough to the pool |

## 7. Budgets

| Unit class | Target bytes | Target depth | Target contracts |
|---|---|---|---|
| Kernel and pure | 16 KiB | 48 | 4 |
| Registry | 24 KiB | 48 | 8 |
| Domain | 24 KiB | 48 | 8 |
| Per-instance account | 16 KiB | 48 | 4 |
| Installer deploy | 48 KiB | 96 | 8 |

Hard fail: 56 KiB, depth 96, 12 contracts. The bootstrap deploy may be 56 KiB only if it
is measured and recorded; every other deploy must stay under 48 KiB.
