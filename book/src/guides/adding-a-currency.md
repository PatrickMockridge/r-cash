# Adding a currency and a market

Adding a currency is configuration, not new product code. The protocol already accepts any
registered currency and any direct pair. What changes is the set of signed deployments that
bring a currency and its first markets to life.

This chapter describes the manual path. On a fresh devnet, `tools/mesh.py install` performs
the same steps for the tracked currency set. The manual path is useful when you are adding a
currency outside the launch set or debugging one step at a time.

## The five steps

### 1. Bring up the feed

A currency needs a price before anything can use it. The sponsor:

1. deploys an `OracleFeed` with the `rcash:oracle-policy:v3` policy;
2. allowlists three reporters;
3. collects signed submissions and activates the feed after the trial.

The policy fixes the quorum, max age, max spread, price band and trial length. A feed that is
not active cannot be bound to a market, and a stale feed stops mint, withdraw, liquidation,
PSM buy/sell and pool trading.

### 2. Deploy the stablecoin system

Deploy `31_stablecoin.rho` with the sponsor's signed v2 parameters:

```
currency, mcrBps, bonusBps, closeFactorBps, ratePerBlock, debtCeiling,
minDebt, maxDebt, maxOracleAge, savingsShareBps, psmFeeBps
```

The deploy verifies the sponsor signature over
`rcash:stablecoin-create:v1|currency|paramsHash|sponsor`, validates the bounds, checks the
params hash, and creates the eight components. It returns:

```
[stablecoinUri, custodyUri, paramsUri, vaultUri, liquidationUri, savingsUri, psmUri, bufferUri, attestation]
```

This is one deploy because the capabilities cannot cross a deploy boundary. A currency
deployment is an installation step, not a browser action.

### 3. List the currency

`CurrencyRegistry.register` takes the eight URIs, the params hash and the sponsor. It verifies
the sponsor signature over the v3 preimage:

```
rcash:currency-register:v3|code|sc|custody|params|vault|liq|savings|psm|buffer|paramsHash|sponsor
```

and the live `attest` (template and currency). It writes the registry entry and the
`StablecoinDirectory` in one commit.

After this step, clients can discover the currency through `ListingViews` and resolve its
asset through `AssetResolver`. A duplicate refuses `"currency exists"` or `"duplicate"`.

### 4. Create the market

A market is created from sponsor-signed 25-field v4 terms. The sponsor signs:

```
rcash:market-create:v1|marketId|termsHash|sponsor
```

`MarketFactory.createMarket` verifies the signature, the terms and both feeds, creates the
pool and lock, binds and seals the directory slot, and stages the index. The market is in
`draft`.

The terms include the base and quote codes, the feed policy hashes, the spreads, the max
trade, the minimum ticket, the seed bounds, the lock terms and the book expiry fields. Every
field is enforced; a terms hash mismatch refuses activation and swap.

### 5. Seed, lock and activate

An LP adds the initial liquidity and funds the seed lock:

- `FxPool.addLiquidity` is allowed on a draft market so the seed can precede activation.
- `LiquidityLock.fund` requires `untilHeight >= now + lockMinBlocks` and takes the LP
  payment.
- `MarketIndex.activate` checks the sealed slot, a funded lock with
  `untilHeight >= lockUntilHeight`, and a pool attestation with matching terms hash, base
  reserve at least `seedBase`, quote reserve at least `max(seedQuote, depthFloorQuote)`, and
  shares at least `seedInitialShares`.

Once active, anyone can trade. The seed LP is locked until the configured height; ordinary LPs
can add and remove later.

## The order matters, but not rigidly

The feed must be active before a market is created. The issuer must be listed before a client
can discover it. The market must be seeded and lock-funded before activation. Beyond those
dependencies, the steps can be automated or run manually.

On a fresh devnet, `make mesh-install` deploys the native systems and feeds and seeds the
priority pairs. `make mesh-pair BASE=... QUOTE=...` creates a non-priority pair. The tracked
config is `configs/mesh.json`; `make mesh-plan` validates it before any deployment.

## The config-driven mesh

`configs/mesh.json` is the source of truth for the supported set:

- `defaultCurrency` is USD;
- `majorCurrencies` are USD, EUR and CNY;
- `currencies` lists the 16 native systems with their tier and initial price;
- `priorityPairs` lists the 24 pairs created and seeded at launch;
- `issuerDefaults`, `feedDefaults` and `marketDefaults` provide the parameter templates.

`tools/mesh.py install` reads this file and performs the deployments. `tools/check_mesh.py`
is the offline gate: it fails if the native set, majors, default, pair count or priority
coverage is wrong, or if an enabled external asset lacks an adapter. The gate never contacts a
node.

## External assets

A bridged asset is not a stablecoin system. It is registered through `registerExternal` with:

- a sponsor signature;
- an adapter attestation;
- `kind: external`;
- `decimals: 8`.

It has no issuer, vault, PSM, savings or liquidation. It is priced by its own feed; the
protocol does not assume a bridged dollar is worth one dollar. It is filtered out of
stablecoin-only screens.

An external asset can be traded in a market once its feed is active and a market is created
for the pair. It cannot be minted, saved or redeemed through an R-Cash issuer.

## A checklist

- [ ] Feed policy signed, three reporters allowlisted, feed activated.
- [ ] Issuer params signed and within bounds; system deploy verified.
- [ ] Currency registered with all eight URIs and a live attestation.
- [ ] Market terms signed; feeds listed and active; factory created the pool and lock.
- [ ] Seed liquidity added; lock funded to the required height.
- [ ] Activation checks pass; the market is `active`.
- [ ] `ListingViews` shows the currency and market; the web mesh matrix renders them.
- [ ] `make check-mesh` passes if the currency is in the tracked config.

> **Where to go deeper.** The currency listing flow is in
> [`docs/spec/30-WIRING.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/30-WIRING.md).
> The market terms are in
> [`docs/SPEC.md` §12.1](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#121-terms).
> The mesh config is `configs/mesh.json`; the external adapter interface is
> [`docs/spec/EXTERNAL-ASSETS.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/EXTERNAL-ASSETS.md).
