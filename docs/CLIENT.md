# Client and SDK

**Status:** R0a (signature parity) is implemented and green on the local devnet. R1/R2 add
the typed protocol operations; R3a adds the browser wallet bindings.

The client stack is Rust, shared by a native CLI and a browser WASM module. TypeScript is
used for the UI and for an independent signer in the parity test. Python remains only as
build-time tooling and the legacy devnet harness.

**Transport:** the native client uses `reqwest` with default features off and speaks
HTTP to the devnet node on port 40403. Public deployments terminate HTTPS at a proxy.

## Crates

| Crate | Responsibility |
|---|---|
| `crates/rcash-core` | Amounts (1e8 base units), validated asset/currency/URI newtypes, Rholang string quoting, the deployment manifest. No I/O. |
| `crates/rcash-chain` | DeployData, signing, REV addresses, devnet key files, the rnode HTTP client, deploy-status polling. |
| `crates/rcash-sdk` | Connected client and deploy lifecycle; protocol operations land here in R1/R2. |
| `crates/rcash-cli` | The `rcash` binary. |
| `crates/rcash-wasm` | wasm-bindgen facade; R0a exports the parity signer. |

The node crates are pinned by git revision in `Cargo.toml`
(`e2d073dcd02f1e560ccb84749937138a1e184b0b`). To hack against a local `../RNodeRust`
checkout without changing the manifest:

```sh
cargo --config 'patch."https://github.com/rchain-community/rchain-rust".rchain-crypto.path="../RNodeRust/crypto"' \
      --config 'patch."https://github.com/rchain-community/rchain-rust".rchain-shared.path="../RNodeRust/shared"' \
      build
```

## What is signed

The SDK uses the node's own cryptography and re-declares only the wire shape:

- `DeployData` is declared locally in `crates/rcash-chain/src/deploy.rs` with the node's
  protobuf field tags: `term=2`, `timestamp=3`, `phloPrice=7`, `phloLimit=8`,
  `validAfterBlockNumber=10`, `shardId=11`, `attachments=12`. **`deployer`, `sig` and
  `sigAlgorithm` are not part of the signed bytes.** It is encoded with prost, and the
  golden bytes pin parity with the node.
- `rchain_crypto::signatures::signed::signature_hash` and
  `Secp256k1::sign_bytes`: BLAKE2b-256 prehash for `secp256k1`, RFC-6979 deterministic
  DER low-S, 65-byte uncompressed public key. The deploy id is the hex DER signature.
  The golden-byte and known-answer tests pin parity with the node.
- `rchain_crypto` also exposes `secp256k1:eth` (raw 64-byte `R||S` over an EIP-191
  keccak hash). That is the only plausible MetaMask route; see `SPIKE-METAMASK.md`.

### Three operational facts that bite

- **Shard id is `/root`** on the devnet. `root` is rejected with
  `Deploy shardId 'root' is not a member of this node's shards: [/root]`.
- **`validAfterBlockNumber` anchors the 50-block lifespan.** A deploy anchored at `0` is
  pooled and never proposed because it is already expired. The CLI reads
  `latestBlockNumber` from `/api/v1/status` and anchors the deploy at the tip.
- **`explore-deploy` has no block context.** Inside it, `rho:block:data` reports height
  `0`. Every arm that checks oracle freshness therefore answers "stale" — `OracleHub.get`
  returns `fresh:false`, `getPair` returns `rate:0`, `pool.quote` refuses, and `book.quote`
  fails. Those reads **must run as signed
  deploys**. The CLI does this; the SDK keeps a public variant only for values that do not
  depend on freshness (price, height, reserves, transfer records, params, reporters).

## Rholang term encoding

The Rholang lexer does not process escapes: a string runs from one `"` to the next, so a
double quote inside a string is unrepresentable and `\n` is two literal characters. The
encoder therefore emits raw text between quotes and **refuses** `"` and control
characters (`rcash_core::rho::quote_str`). Hex enters terms as `"…".hexToBytes()` after
validation. URIs are validated `rho:id:` payloads emitted as backtick literals. Nothing
user-supplied becomes a `new` name; names are generated from a deterministic counter.

Terms are refused before signing above 64 KiB.

## Node HTTP surface

| Operation | Route | Notes |
|---|---|---|
| status | `GET /api/v1/status` | `latestBlockNumber`, `minPhloPrice`, shard |
| deploy | `POST /api/v1/deploy` | body `{data, deployer, signature, sigAlgorithm}` |
| status | `GET /api/v1/deploy-status/{deployId}` | `ProcessedWithSuccess` / `ProcessedWithError` / `NotProcessed` |
| finality | `GET /api/is-finalized/{blockHash}` | separate from deploy status |
| explore | `POST /api/v1/explore-deploy` | body is a bare JSON string; **does not bind `deployerId`** |
| faucet | `POST /api/v1/faucet` | `{address}`, 0.3 REV, dev mode only |
| block | `GET /api/v1/block/{hash}` | |
| last final | `GET /api/last-finalized-block` | |

The public API has permissive CORS; the admin API does not. There is no gRPC-Web.

## Failure taxonomy

| Case | Meaning | Retry? |
|---|---|---|
| transport error | never reached the node | yes |
| deploy rejected | node refused the request | yes, after fixing |
| `ProcessedWithError` | executed and reverted; phlo charged | no; the business error is the answer |
| success + `(false, reason)` | business refusal; no value moved | after fixing the input |
| `StillUnknown` | no status inside the timeout | **never blindly for a value-moving deploy** |

## CLI

```sh
cargo run -p rcash-cli -- keygen --out .devnet/keys.json --names deployer --faucet
cargo run -p rcash-cli -- status
cargo run -p rcash-cli -- address --key deployer
cargo run -p rcash-cli -- deploy --term 'Nil' --key deployer
cargo run -p rcash-cli -- explore --term '...'
cargo run -p rcash-cli -- deploy-status <id>
cargo run -p rcash-cli -- parity-fixture /tmp/rcash-parity.json

# Typed reads (R1). Public reads need no key; balances are one signed deploy.
cargo run -p rcash-cli -- oracle get --currency NGN
cargo run -p rcash-cli -- oracle pair --base NGN --quote KES
cargo run -p rcash-cli -- pool reserves
cargo run -p rcash-cli -- pool quote --asset-in NGN --amount 1
cargo run -p rcash-cli -- transfer info --id 0
cargo run -p rcash-cli -- balance --address <rev-address>
cargo run -p rcash-cli -- account balances --assets REV,NGN,KES --key deployer
```

Public reads call `explore-deploy` and are free. `account balances` needs `deployerId`,
so it is one signed deploy that joins every requested `balance` call; the CLI reports
both the exact decimal and the base-unit count.

### Writes (R2)

All writes are one signed deploy that waits for processing and finality.

```sh
cargo run -p rcash-cli -- account deposit --amount 2 --key deployer
cargo run -p rcash-cli -- convert --from NGN --to KES --amount 1 --key deployer
cargo run -p rcash-cli -- pool add --base 1 --quote 0.09 --key deployer
cargo run -p rcash-cli -- pool swap --asset-in KES --asset-out NGN --amount 1 --key deployer
cargo run -p rcash-cli -- transfer send --source NGN --dest KES --amount 1 --expiry-blocks 60 --key deployer
cargo run -p rcash-cli -- transfer claim --id 4 --dest KES --secret <hex> --key recipient
cargo run -p rcash-cli -- transfer refund --id 5 --dest KES --key deployer
cargo run -p rcash-cli -- oracle submit --currency NGN --price 0.00066666 --index 0 --key reporter1
```

`transfer send` prints the claim secret and a `#/claim/<id>/<secret>` fragment. That
secret is bearer authority; it is printed once and never persisted.

The vault/borrow commands are removed with the old CDP. `devnet demo` is retired until the
v0.4 payment journey is built.

`keygen` writes the plaintext devnet key format the harness already uses. It is local
tooling only; the browser wallet uses the encrypted keystore added in R3a.

## Parity gates

```sh
cargo test --workspace --exclude rcash-wasm
cargo run -p rcash-cli -- parity-fixture /tmp/rcash-parity.json
cd tests/parity && npm ci && node sign-parity.mjs /tmp/rcash-parity.json
wasm-pack test --node crates/rcash-wasm
```

Pinned by those tests:

- the node's REV address vector (`a68a6e…0b76` → `11112VYAt8rUGNRRZX3eJdgagaAhtWTK8Js7F7X5iqddMVqyDTtYau`);
- the node's secp256k1 known-answer signature;
- DeployData golden bytes, including field 12 only when attachments exist;
- Rust ↔ TypeScript byte-identical encoded bytes, public key, DER signature and address;
- native ↔ wasm32 byte-identical signature and address.

Signing is deterministic (RFC-6979), so a mismatch is a defect, not a tolerance.

## MetaMask

The supported signing path is a locally held encrypted key. MetaMask is a read-only
identity until the R0b spike proves otherwise: r-wallet's MetaMask wallet carries only
`ethAddr`/`revAddr`, and every signing path in it rejects MetaMask. See
`SPIKE-METAMASK.md`.

## v0.4 client surface

The installer writes `deployments/devnet-v4.json` with the installed component URIs.
The SDK attaches it with `Client::with_v4_manifest`; the CLI reads it from
`--v4-manifest` (default `deployments/devnet-v4.json`). Currencies and markets are
discovered through the contracts, not the manifest.

Reads (`rcash v4 ...`):

| Command | Contract path |
|---|---|
| `currency CODE` | `ListingViews.currency` → live stablecoin and vault URIs |
| `market BASE QUOTE` | `ListingViews.marketFor` |
| `active MARKET_ID` | `ListingViews.isActive` |
| `slot MARKET_ID` | `MarketDirectory.byId` → pool and lock URIs |
| `lock-info LOCK` | `LiquidityLock.info` |
| `reserves POOL` | `FxPool.reserves` |
| `quote POOL DIR AMOUNT` | `FxPool.quote` (signed: the oracle freshness check needs a block height) |
| `supply STABLECOIN` | `Stablecoin.supply` |
| `transfer-info TRANSFER` | `TransferContract.info` |
| `balance ASSET` | the caller's `Account.balance` (signed; owner-gated) |

Writes (signed by `--key`):

| Command | Flow |
|---|---|
| `fund-rev AMOUNT` | native REV purse → `Account.depositFacet` |
| `send TO_PUB ASSET AMOUNT HASH EXPIRY` | recipient facet lookup → `Account.sendTransfer` |
| `claim TRANSFER SECRET` | `Account.claimTransfer` (secret preimage) |
| `refund TRANSFER` | `Account.refundTransfer` after expiry |
| `swap POOL DIR ASSET_IN ASSET_OUT AMOUNT [--min-out]` | account withdraw → preflight quote → `FxPool.swap` → account deposit |
| `add-liquidity POOL LOCK BASE QUOTE BASE_AMT QUOTE_AMT UNTIL` | both sides from the account → `FxPool.addLiquidity` → `LiquidityLock.fund` |
| `activate MARKET_ID` | anyone may activate a sealed, seeded, lock-funded market |
| `release-lp LOCK POOL BASE QUOTE` | lock release after its height → `FxPool.removeLiquidity` → account deposits |
| `vault-mint VAULT CURRENCY COLLATERAL MINT` | vault deposit → mint → stablecoin into the account |
| `vault-repay VAULT CURRENCY AMOUNT` | account withdraw → `VaultBook.repay` |
| `vault-withdraw VAULT AMOUNT` | `VaultBook.withdraw` → REV into the account |

Live-tested on a fresh devnet through the CLI: `balance` 0 → `fund-rev 0.05` →
5,000,000 base units; `send` → `claim` credited 2,000,000 units and `transfer-info`
reported `claimed`; a second transfer was refunded after expiry and a later `claim`
was refused `closed`. On the market side: `vault-mint` minted 20 V4T against REV,
`add-liquidity` seeded and locked a v2 pool (2,900,015,000 shares), `activate` moved it
to active, and a second key swapped 0.01 REV for 74,775,747 V4T base units.

A quote is a **signed** read on this node: `explore-deploy` has no block context, so the
oracle freshness check would see height 0. The devnet feeds are fresh for
`maxPairAgeBlocks` (50 by default); refresh them before a gated write or the pool refuses
`stale feed` before any funds move.

Amounts accept decimals (`0.05` = 5,000,000 base units) or integers in base units where
the command says `AMOUNT`; `parse_amount` is the one parser.

The wasm facade exposes the same operations as `v4_*` methods on `Rcash`, plus
`claim_hash(secret_hex)`, `public_key()` (needed by a sender) and `height()` (for absolute
transfer expiries). The constructor detects a v0.4 manifest by its `root_uri` field.
