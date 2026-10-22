# R-Cash — Formal Specification (v0.1)

**Status:** devnet prototype; normative for v0.1. **Intent:** [`INTENT.md`](INTENT.md).
**Platform:** rchain-rust at commit `e2d073dcd02f1e560ccb84749937138a1e184b0b`; the Rholang
Mercury interpreter documented in [`PLATFORM.md`](PLATFORM.md). The key words MUST, MUST NOT,
SHOULD, SHOULD NOT and MAY are used as in RFC 2119.

This document specifies the **implemented** v0.1 protocol. Planned components appear only in §15 and
are non-normative.

---

## 1. Scope and conformance

R-Cash v0.1 is a single-corridor payments core: the NGN↔KES corridor, with rNGN and rKES issued by
REV-collateralised CurrencyZones. A conforming implementation MUST provide the contracts, states,
operations, invariants and initialization sequence in §§4–13, under the platform constraints in §14.

The reference implementation is the Rholang in `contracts/src/` and the harness in `harness/`.
Conformance evidence is listed in §14.4.

---

## 2. Terms and notation

| Term | Meaning |
|---|---|
| Deploy | One signed Rholang term executed as one transaction; a reducer error reverts all of its tuple-space and native ERTP/REV writes |
| Block height | Consensus height from `rho:block:data`; the only clock used for staleness and interest |
| Asset | `REV`, `NGN`, `KES`, or `LP:NGN/KES:fpmm` |
| Base unit | `1 whole unit = 100,000,000` (1e8) for every asset; REV's native unit is the drop |
| USD price `P_X` | USD per one whole unit of X × 1e8; e.g. NGN at 1,500/USD is `66,666` |
| Corridor rate `R` | Quote base-units per base base-unit × 1e8; `R = P_base * 1e8 / P_quote` |
| Basis point (bps) | 1/10,000; 10,000 bps = 100% |
| `deployerId` | The deploy's unforgeable signer capability (`rho:rchain:deployerId`); also a bearer capability over that key's native REV |
| `ownerId` | REV address derived from the owner public key; a public account identifier |
| `accountProof` | Unforgeable per-account capability minted by AccountFactory; never returned by `getOrCreate` |
| `vaultAuth` | Unforgeable per-vault capability minted by CurrencyZone.open |
| Claim secret | A caller-chosen byte string, recommended 32 random bytes |
| `claimHash` | `blake2b256(secret)` |
| MCR | Minimum collateral ratio, in bps |
| Deploy height | The block height of the deploy that executes an operation |

---

## 3. System model and authority

### 3.1 Ledger and atomicity

State lives in the RSpace tuple space and the native ERTP/REV stores. A deploy is atomic: if its
execution produces a reducer error, all tuple-space and native changes are reverted (verified,
`docs/PLATFORM.md`). A deploy that ends with an unmatched receive is **not** an error; it is a
successful deploy with a pending continuation. Contracts therefore follow:

- **Reply rule.** Every arm replies exactly once with `(true, value)` or `(false, reason)`.
- **Responder rule.** While a contract holds a consumed state cell, it MUST await only native system
  channels or contracts specified to reply exactly once. It MUST NOT await a caller-supplied
  channel.
- **Validation-before-write.** Checks precede value movement; any unexpected refusal is a hard
  failure (`fail()` = a send forcing `1 / 0`) so the deploy reverts.

### 3.2 Capabilities and authority

Authority is possession of an unforgeable name, a claim secret, or a valid signature. There are no
allowances and no global balance table.

| Authority | Held by | Used for |
|---|---|---|
| `deployerId` | The deploying key's deploy | Account owner authentication only |
| `ownerId` (public) | Everyone | Identifying Accounts and vaults; never authority |
| `accountProof` | The Account contract | Opening/recovering its vault; authorising book send/refund |
| `vaultAuth` | The Account contract | CurrencyZone hot operations |
| Claim secret | Sender and intended recipient/ramp | Claiming an escrowed transfer |
| `bootstrapCap`/unlocked state | The protocol deployer, during installation | Directory registration, Components naming |
| Reporter public key | Allowlisted reporter | Oracle submission |
| Admin public keys | 2-of-3 admins | Oracle/zone/pool parameter changes |

**DeployerId containment (normative).** The Account is the only application contract that receives a
`deployerId`. It makes exactly one read-only call, `deployerId:ops!("pubKeyBytes", *deployerId, ret)`,
compares the result with the stored owner public key, and MUST NOT store, emit, log or use the
`deployerId` for value movement. Other contracts receive `accountProof`, `vaultAuth`, claim secrets
or signatures instead.

### 3.3 Trust assumptions (A1–A10)

- **A1** The three oracle reporters are honest enough that at least two report within tolerance, or
  the feed reports not fresh.
- **A2** Local ramp partners are trusted to pay fiat after redeeming a claim; v0.1 does not use a live
  ramp.
- **A3** Admin keys are held by distinct parties and 2-of-3 is not colluded.
- **A4** The protocol deployer performs the bootstrap and installation sequence without an
  adversarial interleaving.
- **A5** Claim secrets are generated with sufficient entropy and shared only with the intended
  claimant/ramp.
- **A6** REV has a market price that the oracle committee can report; the chain's native vault and
  ERTP ledger are sound.
- **A7** The rchain-rust node is not Byzantine beyond its pre-testnet assumptions; v0.1 is devnet-only.
- **A8** Users understand that the stablecoin is a market instrument, not a bank deposit.
- **A9** A deployer key is not shared; a leaked `deployerId` is a REV-spending capability.
- **A10** Off-chain systems (ramps, wallets, KYC) are outside this specification.

---

## 4. Component topology and initialization

### 4.1 Components

| Component | Cardinality | Where its live channel lives |
|---|---|---|
| Directory | one | registry URI in the deployment manifest; URI also published on `@"rcash:directory"` |
| ComponentRegistry ("Components") | one | registry URI |
| AccountFactory | one | Directory key `component:accounts` |
| Account | one per ownerId | AccountFactory state |
| OracleHub | one | Directory key `component:oracle` |
| CurrencyZone | one per currency | Directory key `component:zone:<CODE>` |
| FxPool | one per corridor | Components key `pool:NGN/KES:fpmm` |
| TransferBook | one per corridor | Components key `transfer:NGN/KES` |

Large contracts (FxPool, TransferBook) are **not** wrapped in a registry bundle in v0.1 because the
node's bundle free-variable check rejects their nested captures. Their live channels are held in
ComponentRegistry; Components is a simple contract and is installed normally.

### 4.2 Directory entries

```
names:
  component:accounts       -> URI(AccountFactory)
  component:oracle         -> URI(OracleHub)
  component:zone:NGN       -> URI(CurrencyZone NGN)
  component:zone:KES       -> URI(CurrencyZone KES)
  component:pools          -> URI(ComponentRegistry)
assets:
  REV                    {kind:"rev",    controllerKey:"system:ertp",          decimals:8}
  NGN                    {kind:"stable", controllerKey:"component:zone:NGN",    decimals:8}
  KES                    {kind:"stable", controllerKey:"component:zone:KES",    decimals:8}
  LP:NGN/KES:fpmm        {kind:"lp",     controllerKey:"pool:NGN/KES:fpmm",     decimals:8}
```

### 4.3 Initialization sequence (normative)

1. **Bootstrap** (one deploy): create Directory, AccountFactory, OracleHub, CurrencyZone rNGN, CurrencyZone
   rKES, ComponentRegistry. Seed reporters/admins/params. Register the Directory names/assets above.
   Lock the Directory. Publish the Directory URI on `@"rcash:directory"`.
2. **Pool setup** (one deploy): create the rNGN/rKES ERTP purses and the LP kit/burn purse; store
   `baseBrand`, `baseIssuer`, `basePurse`, `quoteBrand`, `quoteIssuer`, `quotePurse`, `lpBrand`,
   `lpMint`, `lpIssuer`, `lpBurnFacet` in Components.
3. **Pool deploy** (one deploy): create the FxPool with the live purses/kit; store
   `pool:NGN/KES:fpmm` in Components.
4. **Book deploy** (one deploy): create the TransferBook with the pool, escrow purses and zone
   issuers; store `transfer:NGN/KES` in Components; **lock Components**.
5. The deployment manifest records the Directory, AccountFactory, OracleHub, zone and Components
   URIs and installation markers.

The Components registry is unlocked from step 1 until the end of step 4. A conforming production
deployment MUST make this installation window atomic or use signed/URI-bound registration; in v0.1
it is a trusted deployer sequence (A4). The Directory is locked at the end of step 1 and has no
working admin arm in v0.1; adding a currency or component requires a new bootstrap/deployment.

---

## 5. Common conventions

### 5.1 Reply shapes

| Shape | Meaning |
|---|---|
| `(true, value)` | Success |
| `(false, reason)` | Business refusal; no value moved |
| `fail()` | Reducer error; deploy and all its writes revert |

Reason strings are stable for tests: e.g. `"not owner"`, `"unknown asset"`, `"below MCR"`,
`"stale oracle"`, `"bad secret"`, `"expired"`, `"not open"`, `"above close factor"`, `"locked"`,
`"replay"`, `"signatures"`.

### 5.2 Units and rounding

- All asset amounts are integers in base units (1e8/whole unit), fitting `NonNegI64` for ERTP.
- Prices are integers (`P_X`) at 1e8 per whole unit.
- Intermediate arithmetic MAY promote to `BigInt`; any value that must be an ERTP amount is
  converted with `.toInt()`, which fails closed if it does not fit. There is no silent truncation.
- Outputs of swaps, LP shares and redemptions round **down**; debts, interest, fees and charged
  amounts round **up**.
- Division is integer division; operands are non-negative in every formula in this specification.

### 5.3 Canonical signed payloads

Oracle update:
```
"rcash:oracle:v1|" ++ shard ++ "|" ++ currency ++ "|" ++ price.toString() ++ "|" ++ height.toString()
shard = "/root"
digest = blake2b256(payload UTF-8 bytes)          // exactly 32 bytes
signature = DER secp256k1 over digest
```
Admin action:
```
"rcash:admin:v1|" ++ component ++ "|" ++ nonce.toString() ++ "|" ++ action ++ "|" ++ args.join(",")
```
`args` are strings or integers; strings MUST NOT contain `,` or `|`. `component` is `"oracle"`,
`"zone:NGN"`, `"zone:KES"` or `"pool:NGN/KES:fpmm"`. M distinct admin signatures over the digest are
required; the nonce MUST exceed the stored `govNonce`.

---

## 6. Directory

**State:** `{names: Map<String, String>, assets: Map<String, {kind, controllerKey, decimals}>, locked: Bool, admins: List, threshold: Int, govNonce: Int}`.

| Arm | Args | Auth | Pre | Post / reply |
|---|---|---|---|---|
| `get` | `name` | none | — | `(true, uri)` or `(false, "unknown")` |
| `asset` | `assetId` | none | — | `(true, {kind, controllerKey, decimals})` or `(false, "unknown asset")` |
| `names` | — | none | — | `(true, names)` |
| `register` | `name, uri` | unlocked | `locked == false` | adds/updates `names`; `(true, Nil)` or `(false,"locked")` |
| `registerAsset` | `assetId, kind, controllerKey, decimals` | unlocked | `locked == false` | adds/updates `assets`; `(true, Nil)` |
| `lock` | — | none | — | sets `locked = true`; `(true, Nil)` |
| `admin` | `nonce, action, args, sigs` | — | — | v0.1 returns `(false, "admin actions are phase 2")` |

**Invariants.** `locked` is monotone (false → true). After the bootstrap, no `register`/`registerAsset`
succeeds. `get`/`asset` only read.

---

## 7. ComponentRegistry

**State:** `{locked: Bool, <key>: value | channel, ...}`.

| Arm | Args | Auth | Pre | Post / reply |
|---|---|---|---|---|
| `set` | `key, cap` | unlocked | `locked == false` | stores the channel; `(true, Nil)` |
| `setValue` | `key, value` | unlocked | `locked == false` | stores a value; `(true, Nil)` |
| `lock` | — | none | — | sets `locked = true`; `(true, Nil)` |
| `get` | `key` | none | — | `(true, value)` or `(false, "unknown component")` |
| `has` | `key` | none | — | `(true, Bool)` |

**Invariants.** `locked` is monotone. After the book deploy locks it, no `set`/`setValue` succeeds.
The registry holds `pool:NGN/KES:fpmm` and `transfer:NGN/KES` in v0.1, plus pool setup values.

---

## 8. AccountFactory and Account

### 8.1 AccountFactory

**State:** `Map<ownerId, {account: bundle, proof: name}>`.

| Arm | Args | Auth | Pre | Post / reply |
|---|---|---|---|---|
| `getOrCreate` | `pubKeyBytes` | none | — | derives `ownerId = rho:rev:address("fromPublicKey", pubKey)`; creates an Account if absent; `(true, accountCap, ownerId)`. The proof is never returned |
| `verify` | `ownerId, proof` | — | — | `(true, Bool)` — equality of the presented proof and the stored proof |
| `accountOf` | `ownerId` | none | — | `(true, accountCap)` or `(false, "no account")` |

Anyone MAY create an empty Account for a public key; only the key's deployer can use it because the
Account compares the caller's public key. The `proof` is passed only into the Account at creation.

### 8.2 Account state

```
ownerPubKey : ByteArray            // the owner's 65-byte uncompressed public key
ownerId     : String               // REV address
proof       : name                 // accountProof
purseState  : Map<assetId, {purse: name, brand: value}>
vaultState  : Map<currency, vaultAuth>
directory   : channel              // Directory
```

**Authentication.** Every owner operation takes `*deployerId`, reads its public-key bytes through
`rho:rchain:deployerId:ops`, and compares with `ownerPubKey`. Mismatch → `(false, "not owner")`.
The `deployerId` is never stored, emitted or used for value movement.

### 8.3 Account operations

| Arm | Args | Auth | Semantics |
|---|---|---|---|
| `deposit` | `assetId, payment` | payment is authority | creates the purse lazily via the Directory controller; deposits; `(true, balance)` |
| `depositFacet` | `assetId` | none | lazily creates the purse; `(true, depositFacet)` |
| `withdraw` | `*deployerId, assetId, amount` | owner | `(true, payment)` or `(false, "no purse")` |
| `balance` | `*deployerId, assetId` | owner | `(true, Int)` |
| `openVault` | `*deployerId, currency` | owner | resolves the zone via Directory; `zone.open(ownerId, proof)`; stores `vaultAuth`; `(true, ownerId)` |
| `depositCollateral` | `*deployerId, currency, amount` | owner | withdraws REV from the Account's REV purse; `zone.depositCollateral(ownerId, vaultAuth, payment)` |
| `withdrawCollateral` | `*deployerId, currency, amount` | owner | `zone.withdrawCollateral`; deposits the returned REV payment into the Account |
| `borrow` | `*deployerId, currency, amount` | owner | obtains the stablecoin deposit facet; `zone.borrow` |
| `repay` | `*deployerId, currency, amount` | owner | withdraws stablecoin; `zone.repay` |
| `vaultInfo` | `*deployerId, currency` | owner | `zone.vault(ownerId)` |
| `liquidate` | `*deployerId, currency, victimOwnerId, amount` | owner (spends the caller's stablecoin) | withdraws stablecoin; `zone.liquidate(victimOwnerId, payment)`; deposits the returned REV payment |
| `sendTransfer` | `*deployerId, sourceAsset, destAsset, sourceAmount, minDest, claimHash, expiry` | owner | withdraws source; `book.send(..., ownerId, proof)` |
| `claimTransfer` | `transferId, destAsset, secret` | claim secret | `book.claim`; deposits the returned payment into the Account; `(true, amount)` |
| `refundTransfer` | `*deployerId, transferId, destAsset` | owner | `book.refund(..., ownerId, proof)`; deposits the returned payment |

There is **no `convert` arm** in v0.1; conversion is a client/deploy composition:
`withdraw(source) → pool.swap → deposit(dest)`, atomic in one deploy.

**Asset resolution.** `REV` uses the ERTP `getRevIssuer`; `NGN`/`KES` resolve the zone through the
Directory and call `issuer`/`brand`; `LP:NGN/KES:fpmm` resolves Components → pool and calls
`lpAsset`. Unknown assets are refused.

**Invariants.**
- AC1: A purse is only spent by an owner-authenticated operation, except `claimTransfer`, which is
  authorised by the claim secret and deposits into the Account itself.
- AC2: The `proof` and `vaultAuth` are never emitted to the caller or stored outside the Account and
  the trusted contract that issued them.
- AC3: An Account never holds a consumed state cell across a caller-supplied await; purse creation
  happens before any state consume.

---

## 9. OracleHub

**State:** `{reporters: [ByteArray × 3], prices: Map<currency, Map<index, {price, height}>>, params: {quorum, maxAgeBlocks, maxSpreadBps, minPrice, maxPrice}, admins: [ByteArray], threshold: Int, govNonce: Int}`.

| Arm | Args | Auth | Semantics |
|---|---|---|---|
| `submit` | `currency, price, height, index, pubKey, sig` | reporter signature | index ∈ {0,1,2}; `pubKey == reporters.nth(index)`; payload per §5.3; `height <= now`, `now-height <= 1000`, `height > stored`; stores; `(true, Nil)` or `(false, reason)` |
| `get` | `currency` | none | median of the three latest prices; `fresh` per §9.1; `(true, {price, height, fresh, reason})` |
| `getPair` | `base, quote` | none | `rate = P_base * 1e8 / P_quote`; `(true, {rate, fresh, reason})`; fresh requires both feeds fresh |
| `reporters` | — | none | `(true, [pubKeyHex])` |
| `admin` | `nonce, action, args, sigs` | 2-of-3 | `setParams [quorum, maxAgeBlocks, maxSpreadBps, minPrice, maxPrice]`; `setReporters [hex, hex, hex]`; nonce/replay checks |

### 9.1 Freshness decision

With the three latest prices `p0,p1,p2` and heights `h0,h1,h2`:

- **fresh count** = number of reporters with `0 < h_i <= now`, `now-h_i <= maxAgeBlocks`, and
  `minPrice <= p_i <= maxPrice`.
- **median** = the middle of `p0,p1,p2` by pairwise comparison (odd reporter set).
- **spread** = `max(p0,p1,p2) - min(p0,p1,p2)`.
- `fresh` iff `fresh count >= quorum` AND `median > 0` AND
  `minPrice <= median <= maxPrice` AND `spread * 10000 <= median * maxSpreadBps`.
- The v0.1 spread is computed over all three prices (not only the fresh subset); a stale outlier can
  therefore make the feed not fresh. This is conservative and intentional.

A reporter's update is accepted even if it is a large move (a crash must be reportable); the
`fresh` decision, not the update, is the gate for consumers. Consumers MUST treat `fresh == false`
as "do not borrow, withdraw, swap or quote".

---

## 10. CurrencyZone

**State:** `{currency, vaults: Map<ownerId, {auth: name, collateral: Int, debt: Int, lastHeight: Int}>, totalDebt: Int, totalCollateral: Int, badDebt: Int, params, paused: Bool, admins, threshold, govNonce}`.
**Captured:** stable brand/issuer/mint, burn deposit facet, REV issuer and purse, OracleHub,
AccountFactory, Directory, `bd`, `hash`, `verify`, Guard.

**Params (v0.1):**

| Key | Value |
|---|---|
| `mcrBps` | 20,000 (200%) |
| `bonusBps` | 800 (8%) |
| `closeFactorBps` | 5,000 (50%) |
| `ratePerBlock` | 3,171 (≈5% APR at a 2 s block) |
| `debtCeiling` | 10,000,000,000,000 |
| `minDebt` | 1,000,000 |
| `maxDebt` | 10,000,000,000,000 |

| Arm | Args | Auth | Pre | Post / reply |
|---|---|---|---|---|
| `open` | `ownerId, accountProof` | proof via AccountFactory | proof valid | creates a vault with a fresh `vaultAuth`, or returns the existing auth to the proven owner; `(true, auth)` |
| `depositCollateral` | `ownerId, auth, payment` | vaultAuth | `auth` matches; payment is REV | accrues; credits collateral; deposits into the zone's REV purse; `(true, {collateral, debt})` |
| `withdrawCollateral` | `ownerId, auth, amount` | vaultAuth | `amount>0`; `amount<=collateral`; fresh; post-healthy | accrues; debits; withdraws REV from the zone purse; `(true, payment)` |
| `borrow` | `ownerId, auth, amount, depositFacet` | vaultAuth | not paused; fresh; `rate>0`; `debt+amount <= maxDebt`; `totalDebt+amount <= ceiling`; post-healthy | accrues; mints the stablecoin to the facet; `(true, {debt, health})` |
| `repay` | `ownerId, auth, payment` | vaultAuth | payment is the stablecoin; `amount <= accrued debt` | accrues; deposits into the burn purse; reduces debt and totalDebt; `(true, {debt, repaid})` |
| `liquidate` | `ownerId, payment` | permissionless | payment is the stablecoin; vault unhealthy; `amount <= debt*closeFactorBps/10000` | accrues; burns; seizes `min(collateral, amount*(10000+bonusBps)*1e8/(rate*10000))`; pays REV; `(true, revPayment)` |
| `vault` | `ownerId` | none | — | `(true, {collateral, debt, health, liquidatable, fresh, rate})` |
| `vaults` | — | none | — | `(true, vaults)` |
| `params`, `supply`, `brand`, `issuer`, `currency` | — | none | — | views |
| `admin` | `nonce, action, args, sigs` | 2-of-3 | nonce | `setParams [mcr,bonus,close,rate,ceiling,minDebt,maxDebt]`; `setPaused [0|1]` |

### 10.1 Accrual

On every vault mutation and in the view:
```
interest = ceil(debt * ratePerBlock * (now - lastHeight) / 1e12)
debt'    = debt + interest
lastHeight' = now
```
Simple interest, rounded up; no timestamp is used. `totalDebt` is updated on borrow, repay and
liquidation; interest accrued lazily in a vault is reflected when that vault is touched. The view
reports the accrued debt without mutating.

### 10.2 Health and liquidation

Let `rate` be `OracleHub.getPair("REV", currency).rate` (local base units per REV drop × 1e8).
```
collateralLocal = floor(collateral * rate / 1e8)
healthy         = debt == 0 OR (rate > 0 AND collateralLocal * 10000 >= debt * mcrBps)
```
Liquidation:
```
seized = min(collateral, floor(amount * (10000 + bonusBps) * 1e8 / (rate * 10000)))
debt'  = accrued - amount
collateral' = collateral - seized
badDebt' = badDebt + (if collateral' == 0 then debt' else 0)
```
The liquidator's stablecoin payment is burned (deposited into the burn purse); the REV payment is
withdrawn from the zone's purse. `totalDebt` decreases by `amount`; `totalCollateral` by `seized`.

**Known v0.1 limitation (normative warning).** The `liquidate` arm uses the median rate but does
**not** independently require `fresh == true`; the `vault` view reports `fresh`. A keeper MUST check
`vault(ownerId).fresh == true` before liquidating and MUST treat a stale feed as "do not liquidate".
A stale feed can make the view report `liquidatable == true` while the payout is refused; the keeper
is responsible for the freshness gate.

### 10.3 Zone invariants

- Z1: Stablecoin supply equals `totalDebt` plus any bad debt carried in `totalDebt`; minting occurs
  only in `borrow`, burning only in `repay`/`liquidate`.
- Z2: For every vault, `debt` is non-decreasing except for `repay`/`liquidate`, and collateral changes
  only through `depositCollateral`/`withdrawCollateral`/`liquidate`.
- Z3: After `borrow` or `withdrawCollateral` succeeds, a vault with `debt>0` satisfies the health
  inequality with a fresh rate.
- Z4: A vault's `lastHeight` never decreases; accrual uses a non-negative height delta.
- Z5: The total collateral is the sum of vault collateral; the zone's REV purse balance is at least
  `totalCollateral` (subject to the deploy-atomicity of native writes).

---

## 11. FxPool (oracle-anchored fixed-price market maker)

**State:** `{base, quote, reserveBase, reserveQuote, totalShares, params: {baseSpreadBps, skewSpreadBps, maxTradeBps, minLiquidity}, paused, admins, threshold, govNonce}`.
**Captured:** base/quote ERTP issuers, purses, brands; LP mint, LP issuer, LP burn deposit facet;
OracleHub.

**Params (v0.1):** `baseSpreadBps=20`, `skewSpreadBps=80`, `maxTradeBps=500`, `minLiquidity=1e8`.

| Arm | Args | Auth | Semantics |
|---|---|---|---|
| `quote` | `assetIn, amountIn` | none | fresh, not paused; returns `(true, amountOut, feeBps, rate, maxIn)` or `(false, reason)` |
| `quoteAdd` | `baseAmount` | none | `(true, baseAmount, quoteAmount)` matching the current ratio (first deposit: the oracle ratio) |
| `addLiquidity` | `basePayment, quotePayment, minShares` | payments | verifies both; fresh; not paused; first deposit within 1% of the oracle ratio and mints `MINIMUM_LIQUIDITY` to the burn facet; shares = value − 1e8; later shares = depositValue × totalShares / poolValue; deposits both; mints LP to `ret`; `(true, shares, lpPayment)` |
| `removeLiquidity` | `lpPayment, minBase, minQuote` | LP payment | shares ≤ totalShares; `baseOut = shares*reserveBase/totalShares`, `quoteOut = shares*reserveQuote/totalShares`; slippage checks; burns LP; withdraws both; `(true, basePay, quotePay, shares)` |
| `swap` | `assetIn, payment, minOut` | payment | verifies input; fresh; not paused; max trade; computes output at the oracle rate minus fee; output < output reserve; `minOut`; deposits input; withdraws output; `(true, amountOut, payOut, feeBps)` |
| `reserves` | — | none | `(true, reserveBase, reserveQuote, totalShares, rate, fresh, paused)` |
| `lpAsset` | — | none | `(true, lpBrand, lpIssuer)` |
| `params`, `pair` | — | none | views |
| `admin` | `nonce, action, args, sigs` | 2-of-3 | `setParams [baseSpread, skewSpread, maxTrade]`; `setPaused [0|1]` |

### 11.1 Pricing and fees

```
R       = P_base * 1e8 / P_quote                       // quote base-units per base base-unit ×1e8
value(x)= floor(x_base * R / 1e8) + x_quote           // pool value in quote units
w       = floor(floor(reserveBase * R / 1e8) * 10000 / value)   // base weight, bps
fee     = baseSpreadBps + floor(|w - 5000| * skewSpreadBps / 5000)   // capped by params
base→quote: gross = floor(dx * R / 1e8); out = floor(gross * (10000 - fee) / 10000)
quote→base: gross = floor(dx * 1e8 / R); out = floor(gross * (10000 - fee) / 10000)
maxIn(in) = floor(reserveIn * maxTradeBps / 10000)
```
The fee is taken in the output asset and remains in the reserves; LPs earn it. The skew component
penalises trades that move the pool further from balance; a rebalancing trade pays the base spread.

### 11.2 LP shares

```
first:     value = value(baseAmount, quoteAmount); shares = value - MINIMUM_LIQUIDITY (1e8)
later:     shares = floor(depositValue * totalShares / poolValue)
remove:    baseOut = floor(shares * reserveBase / totalShares)
           quoteOut = floor(shares * reserveQuote / totalShares)
```
The first deposit MUST be within 1% of the oracle ratio; later deposits are priced by the current
pool value and MAY be at a ratio different from the oracle (the LP accepts the inventory mix). The
`MINIMUM_LIQUIDITY` is minted to a purse whose full capability is discarded; only its deposit facet
is retained.

### 11.3 Pool invariants

- P1: `reserveBase` and `reserveQuote` are the pool's internal accounting; each deposit/withdraw is
  matched by a purse movement of the same amount.
- P2: `totalShares` equals the LP minted minus the LP burned; `removeLiquidity` never exceeds
  `totalShares`.
- P3: A swap output is `< reserveOut`; the input is `> 0`; the output is at least `minOut`; the input
  is at most `maxIn`.
- P4: With a fresh rate, the quoted output tracks the oracle rate within the spread/skew; the value
  of the reserves (at the oracle) changes only by fees.
- P5: Rounding favours the pool: outputs floor, required inputs ceil where applicable, LP shares
  floor.

---

## 12. TransferBook

**State:** `{transfers: Map<id, {sender, source, dest, amount, claimHash, expiry, status}>, nextId: Int}`.
**Captured:** FxPool, AccountFactory, base/quote issuers and brands, escrow purses for NGN and KES,
`hash`, `bd`.

`status ∈ {open, claimed, refunded}`.

| Arm | Args | Auth | Semantics |
|---|---|---|---|
| `quote` | `sourceAsset, destAsset, amountIn` | none | only NGN→KES or KES→NGN; forwards the pool quote |
| `send` | `sourceAsset, destAsset, payment, minDest, claimHash, expiry, senderOwnerId, proof` | sender proof via AccountFactory | measures the source payment; pool swap; deposits the destination payment into the escrow purse; records an `open` transfer with `nextId`; `(true, id)` |
| `claim` | `transferId, secret` | claim secret | hashes `secret` with blake2b256; requires `open`, `now <= expiry`, hash match; withdraws `amount` from the escrow; marks `claimed`; `(true, amount, payment)` |
| `refund` | `transferId, senderOwnerId, proof` | sender proof via AccountFactory | requires `open`, `now > expiry`, stored sender == senderOwnerId; withdraws; marks `refunded`; `(true, amount, payment)` |
| `info` | `transferId` | none | `(true, transfer)` or `(false, "no transfer")` |
| `nextId` | — | none | `(true, Int)` |

**Escrow rule.** For each destination asset, the sum of the `amount` of all `open` transfers MUST be
≤ the balance of the book's escrow purse for that asset. The book holds the escrow purses itself and
withdraws exact amounts; it never stores a raw payment in its state.

**Claim/refund exclusivity.** A transfer ID is created once; status transitions are only
`open→claimed` or `open→refunded`; the book consumes its state while withdrawing (a native purse),
so two claims cannot both withdraw. The claim secret is bearer authority: anyone holding it may
claim to their own destination, and the book cannot distinguish the intended recipient. The sender
MUST share the secret only with the intended claimant or ramp.

**Expiry.** Expiry is a block height chosen by the sender. There is no automatic expiry; the sender
(or anyone acting for the sender with the proof) calls `refund` after expiry. An unclaimed transfer
remains `open` and claimable until the expiry is passed.

**No direct-delivery mode in v0.1.** Every transfer is claim-based. A recipient with a wallet can
auto-claim; a recipient without a wallet is served by a ramp that holds the secret.

---

## 13. Economic specification and parameters

### 13.1 CDP parameters

| Parameter | v0.1 | Meaning |
|---|---|---|
| MCR | 20,000 bps | Minimum collateral ratio for borrow/withdraw |
| Liquidation bonus | 800 bps | Seized collateral above the repaid value |
| Close factor | 5,000 bps | Maximum share of debt a single liquidation may repay |
| Stability fee | 3,171 per block (≈5% APR at 2 s blocks) | Simple interest, per-block |
| Debt ceiling | 1e13 base units per currency | Global per-currency cap |
| Min / max debt | 1e6 / 1e13 | Vault size bounds |
| Oracle quorum | 2 of 3 | Fresh reporters required |
| Oracle max age | 50 blocks | Staleness |
| Oracle max spread | 200 bps | Agreement tolerance |
| Oracle absolute band | [1, 1e12] | Price sanity |

### 13.2 Pool and transfer parameters

| Parameter | v0.1 |
|---|---|
| FPMM base spread | 20 bps |
| FPMM skew spread | up to 80 bps |
| FPMM max trade | 500 bps of the input reserve |
| FPMM minimum liquidity | 1e8 LP units burned |
| Transfer fee | none in v0.1; the pool spread is the fee |
| Claim expiry | sender-chosen block height |

### 13.3 Fee flow

The corridor spread (base + skew) is the only protocol-level fee and accrues to the pool's reserves
(hence to LPs). There is no protocol transfer fee, no ramp fee on-chain, and no treasury fee in
v0.1. A ramp's fiat payout fee is off-chain and outside this specification.

---

## 14. Platform conformance and verification

### 14.1 Platform constraints (normative for v0.1)

| Constraint | Consequence |
|---|---|
| Deploy term ≤ 65,536 bytes | bootstrap is minified; large deploys are split |
| Parser nesting depth ≤ 128 | shallow factories; separate pool/book deploys |
| Bundle free-variable check | pool/book are held in Components, not bundled |
| BigInt intermediates do not normalize to Int | `.toInt()` at fixed-point boundaries; fail closed |
| Silent unmatched receive | every arm replies; responder rule |
| Deploy atomicity and native rollback | invariant; verified in phase 0 |
| Name/value quoting and duplicate binders | strict; see `PLATFORM.md` |
| Block height, not timestamp | staleness and interest |

### 14.2 Conformance tests

| Spec area | Evidence | Result |
|---|---|---|
| §3 platform/atomicity/authority | `spikes/` probes + `docs/PLATFORM.md` | 12/12 |
| §6–8 Directory/Accounts | `harness/scenarios/phase1.py` | 7/7 |
| §9 Oracle | `oracle.py` | 19/19 |
| §10 CurrencyZone | `vault.py` | 19/19 |
| §10.2 liquidation | `liquidation.py` | 17/17 |
| §11 FxPool | `pool.py` | 14/14 |
| §12 TransferBook | `transfer.py` | 7/7 |
| End-to-end | `make demo` | exit 0 |

### 14.3 What is not machine-proven

The v0.1 invariants are exercised by scenario tests and property-style checks; they are **not**
mechanically proved. The rchain-rust node carries its own Lean/Coq laws for the interpreter and
consensus; R-Cash does not yet have a machine-checked model. A future formalization should encode
§10.3, §11.3 and §12's escrow/exclusivity invariants as reachability properties over the reducer.

### 14.4 Measurement discipline

Claims labelled "measured" are from the devnet and the pinned node commit; budgets (phlo limits) are
not measurements. The phase-0 report records raw probe evidence; the scenario runners print
per-assertion PASS/FAIL and the harness waits for finality.

---

## 15. Planned components (non-normative)

The following are **not** part of v0.1 and MUST NOT be assumed by a v0.1 client:

- **CPMM backup venue** and a Router that quotes both the FPMM and CPMM and executes the better
  direct venue.
- **Batch payouts** (`TransferBook.sendBatch`): one swap for a total, per-recipient claims/deposits,
  atomic all-or-nothing, surplus returned to the sender.
- **PaymentRequests**: create/pay/cancel single-asset invoices.
- **RampRegistry**: registered on/off-ramp partners per corridor; a mock ramp that redeems claims
  and logs a fiat payout.
- **Direct-delivery transfers** (recipient deposit facet at send time).
- **Multi-hop routing**, **OTC limit orders/RFQ**, protocol fees/treasury, stability pool/bad-debt
  backstop, GHS/UGX/ZAR corridors.
- User CLI/SDK, web UI, cards, platform API, public-testnet deployment, external audit.

---

## 16. Glossary

| Term | Definition |
|---|---|
| CDP | Collateralised debt position; a vault of REV collateral and local stablecoin debt |
| Corridor | A directed pair of local currencies with a pool, oracle pair and ramps |
| DeployerId | The deploy signer's unforgeable capability; also a REV-spending capability |
| ERTP | Electronic Rights Transfer Protocol: brand, mint, issuer, purse, payment |
| FPMM | Fixed-price market maker; quotes at an oracle anchor with spread and inventory skew |
| LP | Liquidity provider; holds LP tokens and earns the spread |
| MCR | Minimum collateral ratio |
| ownerId | Public REV address derived from the owner's public key |
| REV | The chain's native token; 1 REV = 1e8 drops |
| RSpace | The tuple-space store; contract state is held in channels |
| Vault | A CurrencyZone record: collateral, debt, last accrual height, vaultAuth |
