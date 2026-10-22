# Client and SDK

**Status:** R0a (signature parity) is implemented and green on the local devnet. R1/R2 add
the typed protocol operations; R3a adds the browser wallet bindings.

The client stack is Rust, shared by a native CLI and a browser WASM module. TypeScript is
used for the UI and for an independent signer in the parity test. Python remains only as
build-time tooling and the legacy devnet harness.

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
      --config 'patch."https://github.com/rchain-community/rchain-rust".rchain-models.path="../RNodeRust/models"' \
      --config 'patch."https://github.com/rchain-community/rchain-rust".rchain-shared.path="../RNodeRust/shared"' \
      build
```

## What is signed

The SDK calls the node's own code rather than reimplementing it:

- `rchain_models::casper::protocol::casper_message::DeployData`, encoded by its
  `Serialize` impl. Fields `term=2`, `timestamp=3`, `phloPrice=7`, `phloLimit=8`,
  `validAfterBlockNumber=10`, `shardId=11`, `attachments=12`. **`deployer`, `sig` and
  `sigAlgorithm` are not part of the signed bytes.**
- `rchain_crypto::signatures::Signed::new`: BLAKE2b-256 prehash for `secp256k1`, RFC-6979
  deterministic DER low-S, 65-byte uncompressed public key. The deploy id is the hex DER
  signature.
- `rchain_crypto` also exposes `secp256k1:eth` (raw 64-byte `R||S` over an EIP-191
  keccak hash). That is the only plausible MetaMask route; see `SPIKE-METAMASK.md`.

### Two operational facts that bite

- **Shard id is `/root`** on the devnet. `root` is rejected with
  `Deploy shardId 'root' is not a member of this node's shards: [/root]`.
- **`validAfterBlockNumber` anchors the 50-block lifespan.** A deploy anchored at `0` is
  pooled and never proposed because it is already expired. The CLI reads
  `latestBlockNumber` from `/api/v1/status` and anchors the deploy at the tip.

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
cargo run -p rcash-cli -- zone vault --currency NGN --owner <rev-address>
cargo run -p rcash-cli -- transfer info --id 0
cargo run -p rcash-cli -- balance --address <rev-address>
cargo run -p rcash-cli -- account balances --assets REV,NGN,KES --key deployer
```

Public reads call `explore-deploy` and are free. `account balances` needs `deployerId`,
so it is one signed deploy that joins every requested `balance` call; the CLI reports
both the exact decimal and the base-unit count.

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
