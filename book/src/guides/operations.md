# Operations and deployment

R-Cash has two operating environments: a disposable local devnet and a disposable public
testnet. They share the same installer, contracts and clients, but differ in identity, funding
and finality. This chapter describes how a deployment is assembled and what an operator must
check.

## Devnet vs testnet

| | Devnet | Public testnet |
|---|---|---|
| Network id | (development) | `testnet` |
| Shard | `/root` | `/testnet` |
| Validators | 1 | Multiple, 1,000-stake pool |
| Finality | Immediate enough for the harness | More than 2/3 stake; one down keeps it, two stop it |
| Faucet | Local, 0.3 REV | Public, rate-limited |
| Funding | Deployer funded at genesis | Faucet drips and consolidation |
| Keys | `.devnet/keys.json` | Fresh `.testnet/keys.json`, mode 0600 |
| Reset | `make down` and `make devnet` | Operator may rebuild at any time |
| Cost realism | Production REV price | Testnet profile prices REV at \$100 |

The devnet is the reference environment for the behavioural campaign. The testnet is a
rehearsal on a network with latency and multiple validators; it is not an economic or
security test.

## The 17-step install

The bootstrap order is fixed:

```
 1. Root
 2. AdminGuard
 3. Clock / Verifier / Codec
 4. Bounds
 5. Governor
 6. AmmMath
 7. CollateralMath
 8. OracleMath
 9. ClaimCode
10. OracleRegistry
11. OracleHub
12. CurrencyRegistry
13. AssetResolver
14. TransferBook
15. PoolTemplate
16. Market* (terms, directory, index, factory, tradability gate, listing views)
17. AccountFactory
```

Each step registers in `Root`. The installer verifies the expected keys at the carrying
block before the next step:

- the deploy is not in `rejectedDeploys`;
- the block is final;
- every expected `Root` key resolves at that block's post-state.

The installer target runs with `--fresh`; if a step is already present, the installer skips it
and reads the existing entry. A re-run is therefore safe. The manifest is written only after
the final step.

The order is not cosmetic. `OracleRegistry` must exist before a currency can be listed.
`AssetResolver` must exist before an account can create a purse. `PoolTemplate` must exist
before a market factory can create a pool. `AccountFactory` is last because it depends on the
asset layer.

## The operation cache

Every installer step has an operation id and a write-ahead signed body cached in
`.testnet/ops`. A transport retry reuses the exact signed bytes, so it cannot accidentally
create a second install step with a new timestamp or nonce. This is the operational equivalent
of the payment opId:

- a cached retry is idempotent;
- a new operation id is a new intent;
- a value-moving deploy is never retried blindly.

The cache records the node that accepted the deploy. A cached retry is pinned to that node,
including across a restart.

## Manifests

`deployments/devnet-v4.json` is the component manifest. It lists component URIs, not
capabilities and not keys. It is written only after a complete install.

`.testnet/testnet-v4.json` is the testnet manifest. Systems and markets are **not** in the
manifest; clients discover them through `ListingViews`. A separate systems manifest does not
exist and should not be invented.

The web app copies the devnet manifest to `web/public/devnet.json` with
`scripts/sync-manifest.mjs`. The WASM constructor recognises a manifest by its `root_uri`
field.

## Root resolution

Every contract resolves what it needs through `Root` at arm entry. A cold-path helper is:

```
resolve(key) -> (uri, version) | (false, reason)
lookup(uri)  -> cap
```

An unknown key or a retired entry is a refusal. A resolved capability is never cached across
arms. The installer uses a signed `Root.resolve` read to verify a step; the same read is what
a client uses to discover the component.

## Configuration

| File | Purpose |
|---|---|
| `configs/testnet.json` | Network id, shard, genesis, endpoints, faucet, phlo, ticker, lock blocks, timeouts, mesh config, REV price |
| `configs/mesh.json` | Supported currencies, majors, USD default, priority pairs, parameter templates |
| `configs/mesh-testnet.json` | Mesh price-level variant for the public faucet |
| `.devnet/keys.json` | Devnet keys (gitignored) |
| `.testnet/keys.json` | Testnet keys (gitignored, mode 0600) |
| `.testnet/testnet-v4.json` | Testnet manifest (gitignored, public URIs only) |

The tracked configs are the source of truth. Do not hard-code a genesis or an endpoint in a
client; read the profile.

## Deployment artifacts

A complete install produces:

- the component manifest;
- a state file recording each step, its operation id and the carrying block;
- the generated build terms under `contracts/build/`;
- the deployment logs.

The artifacts are operational evidence. A campaign report records the source SHA, node
version, image digest, memory, timestamps and the per-requirement result. A green static gate
is not a substitute for the campaign report.

## What can go wrong

| Failure | Meaning | Response |
|---|---|---|
| A step does not resolve | The deploy executed but the key is missing | Re-run; the op cache is idempotent |
| A step is rejected | Signature, phlo, shard or term size | Fix the input; do not retry blind |
| The manifest is partial | Install did not finish | Re-run from the last good step; the manifest is written only at the end |
| Genesis changed | The chain was rebuilt | New keys, new manifest, new campaign |
| Node is throttled | Resource admission | Wait for `acceptsDeploys: true`; do not bypass |
| Finality stalls | Not enough validators | Treat as BLOCKED; do not report a pass |

## The rule that matters

A deployment is **PASS** only with the evidence bundle, or **BLOCKED** with the upstream
blocker. A blocked stage is never reported as conformance. This is a normative operations
requirement, not a style preference.

> **Where to go deeper.** The install order and lifecycle are in
> [`docs/spec/30-WIRING.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/30-WIRING.md).
> The operations requirements are in
> [`docs/SPEC.md` §17](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#17-operations).
> The testnet procedure is in [The public testnet](testnet.md).
