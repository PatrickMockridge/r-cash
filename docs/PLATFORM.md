# Platform notes

## Pinned node

- Repository: the `rholo` checkout (default `../rholo`, override `RHOLO_DIR`)
- Commit at the start of this build: `e2d073dcd02f1e560ccb84749937138a1e184b0b`
- The local image is built from the checked-out working tree; pin the commit when reproducing.
- Local image: `rnode:local` (built by `tools/devnet.sh build`).

## Devnet

```sh
cd $RHOLO_DIR && tools/devnet.sh build
cd $RHOLO_DIR && tools/devnet.sh up --validators 1
```

- Container `devnet-bootstrap`; public HTTP 40403; admin HTTP 40405; deploy gRPC 40402.
- Deployer = validator 0, funded with 10,000 REV; faucet drips 0.3 REV, 1/second.

## Hard platform limits found while building

These are measured, not assumptions:

1. **Deploy term size: 65,536 bytes.** Larger terms are refused before parsing (`deploy term is N
   bytes; this node parses at most 65536`). The bootstrap is ~57 KB rendered; the build/deploy path
   minifies it (comments/indentation only) to ~34 KB. `tools/minify_rho.py` is string-aware.
2. **Parser nesting depth: 128.** Deeply nested terms fail with `parse depth exceeded`. The shallow
   pool factory and the split deploys were a direct response.
3. **Bundle free-variable check.** `bundle+{*c}` is refused when the quoted contract captures some
   nested contract parameters (`Bundle's content must not have free variables or wildcards`). The
   zone factory happens to pass; the pool/book do not. Workaround: hold large contracts' live names
   in `ComponentRegistry` instead of registering a bundle. The bootstrap creates the registry; the
   pool setup/deploy and transfer deploy publish names there. The registry is unlocked only during
   installation and is locked by the TransferBook deploy; the installation window is trusted (A4).
4. **BigInt intermediates are not normalized.** Rholang promotes any overflow to `BigInt`, and the
   `Int` type pattern does not match a `BigInt` even when the value fits. Use `.toInt()` at the
   fixed-point boundary; it errors if the value does not fit (fail closed).
5. **Name/value quoting.** A name bound by a receive (or a bare contract parameter) used as a send
   argument needs `*x`; a value bound by `@x` in a tuple is passed bare. Mixing these is a parse
   error (`Name variable: x used in process context` / `Proc variable: x used in Name context`).
   Duplicate channel names in mutually exclusive branches of one arm are rejected as duplicate
   binders; give each branch distinct channels.
6. **A failed deploy reverts tuple space and native ERTP/REV state** (verified in phase 0).
7. **An unmatched `for` is silent**; it is not an error. A state cell consumed and then awaiting a
   dead name is committed consumed (verified in phase 0). Every arm replies; every hot-path await is
   a native channel or a contract specified to reply exactly once.

## Measured costs (phase 0)

| Operation | Phlo |
|---|---|
| Counter install (small probe) | 2,777 |
| Counter call | 2,946 |
| Block data probe | ~1,000 |
| ERTP purse install | install cost measured in `spikes/REPORT.md` |

Larger deploys (bootstrap 30-100M phlo, pool 40/80M, transfer book 80M) are budgets, not measured
actuals; the block's `deploys[].cost` is the authority. Record actuals when the demo is run.

## Finality

DAG finality via `GET /api/is-finalized/{hash}`; every state claim in the harness waits for it.
Deploy status alone is not finality.

## Client integration findings (R0-R3)

These were found while building the Rust/WASM client and are enforced in code or documented
for anyone building another client.

1. **Shard id is `/root`.** A deploy with `shardId: "root"` is refused:
   `Deploy shardId 'root' is not a member of this node's shards: [/root]`.
2. **`validAfterBlockNumber` anchors a 50-block lifespan, not just a validity floor.** A
   deploy anchored at `0` is accepted into the pool and never proposed because it is
   already expired. The client reads `latestBlockNumber` from `/api/v1/status` and anchors
   every deploy at the tip.
3. **`explore-deploy` has no block context.** `rho:block:data` reports height `0` inside it.
   Oracle freshness checks therefore fail there: `OracleHub.get` says `fresh:false`,
   `getPair` returns `rate:0`, `pool.quote`/`quoteAdd` refuse, `zone.vault` computes health
   with rate 0, and `book.quote` fails. Freshness-gated reads must be signed deploys.
4. **`i64` crosses wasm-bindgen as `BigInt`.** Methods taking a block height or transfer id
   take `bigint` on the JS side; the web app converts explicitly. Amounts stay decimal
   strings and are parsed exactly in Rust.
5. **`std::time::{Instant, SystemTime}` panic on wasm32-unknown-unknown.** The client uses
   `web-time` for `Instant`/`SystemTime` and `gloo-timers` for sleeps.
6. **The node crate wasm requirements** hold: `getrandom_backend="wasm_js"` in
   `.cargo/config.toml`, and `rchain-shared` is linked with `default-features = false`.
7. **HTTP surface used by the client:** `POST /api/v1/deploy`, `GET /api/v1/deploy-status/{sig}`,
   `GET /api/is-finalized/{hash}`, `POST /api/v1/explore-deploy` (bare JSON string body),
   `POST /api/v1/faucet`, `GET /api/v1/status`, `GET /api/v1/block/{hash}`. The public
   listener has permissive CORS; the admin listener does not. There is no gRPC-Web.
