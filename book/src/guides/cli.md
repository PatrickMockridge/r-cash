# The CLI

`rcash` is the reference client. It exposes the same SDK operations as the web app, in a form
that is easy to script and to use for operations. It is also the client the installer uses
for cached, idempotent deploys.

Build it from the repository root:

```sh
cargo build -p rcash-cli
./target/debug/rcash --help
```

Most examples assume a running devnet with the components installed
([quickstart](quickstart.md)). The CLI reads `deployments/devnet-v4.json` by default; pass
`--v4-manifest` to point elsewhere.

## Global options

| Option | Purpose |
|---|---|
| `--node URL` | Node HTTP endpoint (default `http://localhost:40403`) |
| `--keys PATH` | Keystore file (default `.devnet/keys.json`) |
| `--key NAME` | Key to sign with |
| `--shard-id ID` | Shard id; devnet `/root`, testnet `/testnet` |
| `--v4-manifest PATH` | Component manifest |
| `--display-currency CODE` | Human display currency (USD default); `RCASH_DISPLAY_CURRENCY` also works |
| `--json` | Machine-readable output |
| `--nodes A,B` | Known endpoints; the hostlist augments them |
| `--no-hostlist` | Disable discovery; use `--node`/`--nodes` only |

## Working against a local rholo checkout

The node crates are pinned by git revision in `Cargo.toml`. To hack against a local `../rholo`
checkout without changing the manifest:

```sh
cargo --config 'patch."https://github.com/rhovision-org/rholo".rchain-crypto.path="../rholo/crypto"' \
      --config 'patch."https://github.com/rhovision-org/rholo".rchain-shared.path="../rholo/shared"' \
      build
```

The pinned commit is recorded in `Cargo.toml` and `THIRD_PARTY_NOTICES.md`. The license is
AGPL-3.0-only; a modified version served over a network must offer its source.

## Keys and status

```sh
rcash keygen --out .devnet/keys.json --names deployer --faucet
rcash status
rcash address --key deployer
rcash doctor --json
```

`keygen` writes the plaintext devnet key format the harness uses. It is local tooling; the
browser uses an encrypted keystore instead. `status` reads the node's height, shard and
minimum phlo price. `doctor` reports the node, manifest and hostlist state.

## Deploy and explore

```sh
rcash deploy --term 'Nil' --key deployer
rcash explore --term '...'
rcash deploy-status <deploy-id>
rcash parity-fixture /tmp/rcash-parity.json
```

`deploy` signs and submits a term, waits for processing and finality, and reports the result.
`explore` runs a term without a deployer identity; it is free but has **no block context**, so
freshness-gated reads do not work there. `parity-fixture` emits the bytes used by the
signature parity tests.

## Typed reads

Public reads use `explore-deploy` and cost nothing:

```sh
rcash oracle get --currency NGN
rcash oracle pair --base NGN --quote KES
rcash pool reserves
rcash pool quote --asset-in NGN --amount 1
rcash transfer info --id 0
rcash balance --address <rev-address>
```

A freshness-gated read must be a signed deploy:

```sh
rcash pool quote ...          # signed; needs a key
rcash account balances --assets REV,NGN,KES --key deployer
```

`account balances` joins every requested balance in one signed deploy and reports the exact
decimal and the base-unit count.

## Writes

All writes are one signed deploy that waits for processing and finality.

```sh
rcash account deposit --amount 2 --key deployer
rcash convert --from NGN --to KES --amount 1 --key deployer
rcash pool add --base 1 --quote 0.09 --key deployer
rcash pool swap --asset-in KES --asset-out NGN --amount 1 --key deployer
rcash transfer send --source NGN --dest KES --amount 1 --expiry-blocks 60 --key deployer
rcash transfer claim --id 4 --dest KES --secret <hex> --key recipient
rcash transfer refund --id 5 --dest KES --key deployer
rcash oracle submit --currency NGN --price 0.00066666 --index 0 --key reporter1
```

`transfer send` prints the claim secret and a `#/claim/<id>/<secret>` fragment. The secret is
bearer authority; it is printed once and never persisted. The optional `--memo`, `--op-id`
and `--stipend` flags map to the payment features described in
[Payments and claim links](../mechanisms/payments.md).

## The `v4` group

The v4 surface covers the installed components. Reads:

| Command | What it reads |
|---|---|
| `v4 currency CODE` | Listing entry and live stablecoin/vault URIs |
| `v4 currencies` | All listed currencies, including `kind` and external metadata |
| `v4 market BASE QUOTE` | Either orientation of an unordered pair |
| `v4 active MARKET_ID` | Whether the market is active |
| `v4 slot MARKET_ID` | Pool and lock URIs |
| `v4 lock-info LOCK` | Lock state and countdown |
| `v4 reserves POOL` | Pool reserves |
| `v4 quote POOL DIR AMOUNT` | Signed quote (freshness needs a block height) |
| `v4 supply STABLECOIN` | Stablecoin supply |
| `v4 transfer-info TRANSFER` | Transfer record |
| `v4 vault VAULT`, `v4 totals VAULT` | Vault and issuer totals |
| `v4 savings-info`, `v4 savings-position` | Savings pool and owner position |
| `v4 psm-info`, `v4 buffer-info`, `v4 risk-params`, `v4 pending` | Economic state and governance |

Writes:

| Command | Flow |
|---|---|
| `v4 fund-rev AMOUNT` | Native REV → account deposit facet |
| `v4 send TO_PUB ASSET AMOUNT HASH EXPIRY [--memo] [--op-id] [--stipend]` | Recipient facet lookup → `Account.sendTransfer` |
| `v4 claim TRANSFER SECRET` | `Account.claimTransfer` |
| `v4 refund TRANSFER` | `Account.refundTransfer` after expiry |
| `v4 swap POOL DIR ASSET_IN ASSET_OUT AMOUNT [--min-out]` | Account withdraw → preflight quote → pool swap → account deposit |
| `v4 add-liquidity POOL LOCK BASE QUOTE BASE_AMT QUOTE_AMT UNTIL --min-shares N` | Both sides → pool → lock |
| `v4 activate MARKET_ID` | Activate a sealed, seeded, lock-funded market |
| `v4 release-lp LOCK POOL BASE QUOTE --min-base B --min-quote Q` | Lock release → remove liquidity → deposits |
| `v4 vault-open VAULT` | `Account.vaultOpen` |
| `v4 vault-deposit VAULT AMOUNT` | Account withdraw → `VaultBook.deposit` |
| `v4 vault-mint VAULT CURRENCY COLLATERAL MINT` | Deposit → mint → account |
| `v4 vault-repay VAULT CURRENCY AMOUNT` | Withdraw → repay (principal burn, interest to buffer) |
| `v4 vault-withdraw VAULT AMOUNT` | Withdraw collateral → account |
| `v4 vault-liquidate LIQUIDATION CURRENCY OWNER AMOUNT MIN_COLLATERAL` | Repay → seize REV → account |
| `v4 savings-deposit SAVINGS CURRENCY AMOUNT` | Account → savings pool |
| `v4 savings-withdraw SAVINGS CURRENCY SHARES` | Pool → account |
| `v4 psm-buy PSM CURRENCY REV_AMOUNT MIN_STABLE` | REV → PSM → stablecoin |
| `v4 psm-sell PSM CURRENCY AMOUNT MIN_REV` | Stablecoin → PSM → REV |
| `v4 create-market TERMS.json` | Sign terms → factory |
| `v4 market-status MARKET STATUS NONCE SIGS…` | Governor-gated status |
| `v4 pause-currency CODE PAUSED NONCE SIGS…` | Governor-gated pause |

Amounts accept decimals (`0.05` = 5,000,000 base units) or integers in base units. The parser
refuses more than eight decimals; there is no float path.

## Node hostlist and pools

A node can publish a **hostlist**: the live peers it has probed and found deploy-capable. The
client discovers it lazily, caches it for 30 seconds, and falls back to its configured seed on
404, an empty list or any failure. This lets one client binary work against today's testnet
(whose pinned binary has no hostlist) and spread load automatically once a hostlist-enabled
node is pinned. Discovery is an optimization, not a gate: if it is absent or fails, the seed
and any `--nodes` endpoints are used immediately.

Entries are advisory. Before use, the client re-verifies each one with
`GET {httpUrl}/api/v1/status` and requires:

- `networkId` and `shardId` to match the client;
- `proposer: true`;
- `/status.address` to name the advertised `nodeId`;
- a usable scheme: `http` for the native client (it has no TLS backend), `https` for a
  browser whose seed is HTTPS. A hostlist advertises `http://ip:40403`, so an HTTPS page
  ignores those entries and keeps its HTTPS seed.

Routing follows the node's guidance:

- **Reads** round-robin over verified endpoints and fail over on transport errors, 429, 503,
  5xx and decode errors. The seed is the last resort. `deploy-status` tries the deploy's
  bound node first.
- **Writes** are signed for exactly one node and sent there once. The client ranks targets for
  cost and speed — accepting nodes first, then the lowest `minPhloPrice`, then the freshest
  tip — and round-robins inside the cheapest accepting tier so concurrent deploys spread
  without paying more. It fetches the chosen node's live status, anchors
  `validAfterBlockNumber` at the lowest relevant tip (so relayed copies stay inside every
  peer's 50-block window), and prices at `max(configured, target.minPhloPrice)` — the floor of
  the one node that receives it, so choosing a cheaper node actually pays less. On 429, 503, a
  timeout or any transport error it **does not re-submit the same signed bytes elsewhere**.
  The caller either retries the same node or proves the effect absent and re-signs under a new
  operation id.
- The op cache records the chosen node. A cached retry is pinned to it, including across a
  restart.

The node-side relay (`RNODE_DEPLOY_RELAY`) is operator-only: each admitted deploy is copied
to connected peers over gRPC. It is a copy, not a move; clients do not enable or depend on it.

```sh
# discover from the seed (the default)
rcash --node http://seed:40403 status

# known endpoints are added to the background hostlist (or used alone when it is absent)
rcash --nodes http://a:40403,http://b:40403 deploy --term 'Nil' --key deployer

# turn discovery off entirely
rcash --no-hostlist status

# inspect what was discovered
rcash --node http://seed:40403 doctor --json
```

The WASM facade exposes `set_nodes`, `set_hostlist`, `node_list` and `discover_nodes`.

## Failure taxonomy

| Case | Meaning | Retry? |
|---|---|---|
| Transport error | Never reached the node | Yes |
| Deploy rejected | Node refused the request | Yes, after fixing |
| `ProcessedWithError` | Executed and reverted; phlo charged | No; the business error is the answer |
| Success + `(false, reason)` | Business refusal; no value moved | After fixing the input |
| `StillUnknown` | No status within the timeout | **Never blindly for a value-moving deploy** |
| `HostlistUnsupported` | The seed returns 404 for `/api/v1/nodes` | No; use the seed alone |
| Network/shard mismatch | Hostlist is for another chain | No; re-check the profile |
| `NoEligibleNode` | No verified proposer answered | After the node recovers |

Discovery errors are configuration or transport facts, not protocol refusals. The CLI exits
3 for them, not the refusal exit 4.

## Signature parity

The client signs the node's `DeployData` bytes with the node's secp256k1 path. Parity is a
blocking gate:

```sh
cargo test --workspace --exclude rcash-wasm
rcash parity-fixture /tmp/rcash-parity.json
cd tests/parity && npm ci && node sign-parity.mjs /tmp/rcash-parity.json
```

The tests pin the node's REV address vector, the secp256k1 known-answer signature, the
DeployData golden bytes, byte-identical Rust/TypeScript output and byte-identical native/wasm
output. Signing is deterministic (RFC-6979); a mismatch is a defect, not a tolerance.

## MetaMask

The supported signing path is a locally held encrypted key. MetaMask is a read-only identity
until a signing spike proves otherwise. The web wallet keeps the key inside WASM and stores an
encrypted keystore in IndexedDB.

> **Where to go deeper.** Client requirements are in
> [`docs/SPEC.md` §15](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#15-clients-rust-sdk-cli-wasm).
> The deploy format and signing path are in
> `crates/rcash-chain/src/deploy.rs`. The web journey is in [The web app](web-app.md).
