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
| `Bounds` | none | `checkIssuer`, `checkFeed`, `checkPool`, `checkBook`, `checkTerms` | Pure on-chain bounds for every canonical group. |
| `AdminGuard` | none | `verify(domain, nonce, action, argsHash, sigs, admins, threshold)` | Threshold signature verification over `rcash:admin:v1|domain|nonce|action|args`. |
| `AmmMath` | none | `value`, `weight`, `fee`, `out`, `shares` | Pure FPMM arithmetic, floor outputs and shares. |
| `OracleMath` | none | `median3`, `fresh`, `rate` | Median, spread, freshness, cross rate. |
| `ClaimCode` | none | `hash(secret)` | Claim-secret hashing. |

### v0.4 stablecoin issuer

| Component | State | Interface | Responsibility |
|---|---|---|---|
| `Stablecoin` | `issuerState` | `brand`, `issuer`, `supply`, `mint`, `burn`, `amountOf`, `attest` | Owns the ERTP kit. Only the VaultBook holds the scoped mint/burn caps. |
| `CollateralCustody` | none; REV purse in closure | `deposit`, `withdraw`, `balance`, `attest` | Holds the currency's REV purse; only the VaultBook holds the custody cap. |
| `RiskParameters` | none; params in closure | `params`, `attest` | Immutable MCR, bonus, close factor, rate, ceiling, min/max debt and max oracle age. |
| `VaultBook` | `vaultState` | `open`, `deposit`, `mint`, `withdraw`, `repay`, `liquidate`, `vault`, `vaults`, `totals`, `params`, `pause`, `attest` | Atomic vault/accounting cluster. Enforces health, ceiling, min/max debt, close factor and pause; no second principal ledger. |
| `CollateralMath` | none | `accrue`, `health`, `payout`, `seize` | Pure issuer arithmetic; replaces the deleted RiskMath. |
| `LiquidationEngine` | none | `liquidate`, `attest` | Holds the only liquidation capability. Permissionless callers burn stablecoin and receive REV; the VaultBook keeps the accounting. |
| `CurrencyRegistry` | `currencyState` | `register`, `currency`, `currencies`, `setPaused` | Sponsor-signed currency listing. Verifies the live stablecoin attestation, then writes the directory. |
| `StablecoinDirectory` | `stablecoinDirectoryState` | `register`, `lookup`, `entries` | The one code → system index. Only the registry holds its write capability. |

The system is deployed per currency by the signed `31_stablecoin.rho`: the deploy verifies
the sponsor signature, bounds and params hash before it creates anything. The directory and
registry are one deploy (`32_currency_registry.rho`); there is no separate on-chain
factory in v0.4, because the creation path is already signature- and bounds-gated.

## 2. Authority and discovery

| Component | State | Interface | Responsibility |
|---|---|---|---|
| `Governor` | `governorState` | `authorize(domain, nonce, action, argsHash, sigs)`, `admins()`, `admin(...)` | Owns the admin set, threshold and per-domain nonce. Units call `authorize` and apply the verified intent. `AdminGuard` is its pure verifier. |

`Root` is the only singleton directory. Per-instance URIs live in `StablecoinDirectory`, `OracleRegistry` and `MarketDirectory`. `Directory` and `ComponentRegistry` are deleted.

## 3. Registries

| Component | State | Interface | Responsibility |
|---|---|---|---|
| `CurrencyRegistry` | `currencyState` | `register`, `currency`, `currencies`, `setPaused` | Currency records. Registration requires a sponsor signature over the system URI and params hash, and the live stablecoin attestation; the registry then writes `StablecoinDirectory(code)`, so the directory match is structural. Status is `active` or `paused`; pause is governor-gated. |
| `MarketTerms` | `termsState` | `put`, `get`, `boundsOk` | Content-addressed `termsHash → {terms, values}`. `put` recomputes the hash and rejects a mismatch. |
| `MarketIndex` | `marketState` | `stage`, `activate`, `pause`, `delist`, `cancel`, `market`, `marketFor`, `status`, `isActive`, `admin` | Market status, pair uniqueness, version monotonicity and nonce in one cell. |
| `MarketDirectory` | `directoryState` | `bind`, `seal`, `unseal`, `byId`, `slot` | Per-market `{poolUri, bookUri, lockUri, termsHash, sealed}`. Only `MarketFactory` writes; a draft slot may be overwritten, then sealed. |
| `OracleRegistry` | `oracleRegState` | `registerFeed`, `feedEntry`, `reporters`, `allowlist`, `admin` | Reporter allowlist and per-currency feed URI plus policy hash. |

## 4. Domain components

| Component | State | Interface | Responsibility |
|---|---|---|---|
| `OracleFeed` (currency) | `feedState` | `submit`, `get`, `activate`, `info`, `admin` | Per-currency feed deployed by the sponsor and bound by `OracleRegistry`; no factory. |
| `OracleHub` | none | `get`, `feedStatus`, `getPair`, `reporters` | Stateless router; `getPair(base, quote, maxAgeBlocks)` returns per-feed freshness and ages. Callers enforce their own age bound. |
| `MarketFactory` | none | `createMarket(terms, values, sponsor, sig)` | Verifies the sponsor signature, the live feed policy hashes and `Bounds.checkTerms`; resolves `PoolTemplate`, binds and seals the pool URI in `MarketDirectory`, and stages `MarketIndex`. |
| `FxPool` (market, R) | `poolState` | `pair`, `reserves`, `attest`, `quote`, `swap`, `addLiquidity`, `removeLiquidity` | Oracle-anchored pool: base/quote purses and LP kit created by `PoolTemplate`, reserves and shares in one cell, fee from `AmmMath` weight/skew. |
| `LiquidityLock` (market, R) | `lockState` | `fund`, `release`, `cancel`, `info` | Created by `PoolTemplate` with the pool. One-shot LP custody: the funder records the beneficiary and height; only the beneficiary's `deployerId` can release after the height; cancel is governor-gated. |
| `PoolTemplate` | none | `create` | Resolves the base/quote issuers, creates the purses and LP kit, assembles the `FxPool` and returns its URI; the factory owns the directory/index writes. |
| `TransferBook` | `bookState` | `send` | Allocates transfer ids and creates a registered `TransferContract` per transfer. It never holds escrow; the per-transfer cell does. |
| `TransferContract` (transfer, R) | `transferState` | `claim`, `refund`, `info` | Authoritative transfer object: payment in closure, status in one cell. Claim and refund consume the cell and re-post a terminal `claimed`/`refunded` status, so later calls reply `closed` rather than stalling. Claim requires the secret preimage; refund requires expiry and the sender's `deployerId`. |
| `TradabilityGate` | none | `admit(status, fresh, value, inputValue, terms)` | Pure policy verdict; receives all inputs and never calls back into the pool. |
| `AccountFactory` | `factoryState` | `getOrCreate`, `verify`, `accountOf` | One account per owner. `getOrCreate` creates the `Account`, `PurseStore` and `AccountGate`; the vault proof is created inside the account contract and never returned or passed through a message. |
| `Account` (owner, R) | none; `PurseStore` and proof in closure | `vaultOpen`, `deposit`, `withdraw`, `balance`, `depositFacet`; transfer arms next | Owner-authenticated thin payment router. Every arm takes the caller's `deployerId`, checks it in `AccountGate`, then routes to `PurseStore`; no vault state. |
| `PurseStore` (owner, R) | `purseState` | `ensure`, `deposit`, `withdraw`, `balance`, `facet` | One ERTP purse per asset, created through `AssetResolver`; `balance` reads the purse's `getCurrentAmount`. |
| `AccountGate` (owner, R) | none | `verify` | Derives the caller's REV address from `deployerId` and compares it with the owner; no state. |
| `TransferClient` | none | `send`, `claim`, `refund`, `info` | Account-side transfer orchestration; resolves the book and market. |
| `AssetResolver` | none | `issuer(assetId)`, `kind(assetId)` | `REV` resolves through ERTP; every other id resolves through `CurrencyRegistry` and the live `Stablecoin`. Resolution happens at arm entry; no registry capability is cached. |
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
