# Third-party notices

R-Cash itself is licensed **AGPL-3.0-only** (see `LICENSE`). Code committed through
`d5d613b` was Apache-2.0; those grants are not revoked. The client migration commit and
later are AGPL-3.0-only.

## Linked dependencies

| Component | License | Use in R-Cash | Obligations |
|---|---|---|---|
| [rholo](https://github.com/rhovision-org/rholo) `rchain-crypto`, `rchain-shared` | AGPL-3.0-only | Hashing, secp256k1 signing, serialization helpers. `DeployData` is declared locally with the node's field tags. Pinned to commit `841cb842876369deaa63e3b3e26c20d60e6c74c6`. | The source URL and commit are recorded in `Cargo.toml` and `book/src/guides/cli.md`. This repository is distributed under the same license. Anyone running a modified version over a network must offer its source (AGPL §13). |
| [RhoGov](https://github.com/rhovision-org/rhogov) `src/chain/keys.ts`, `keystore.ts`, `node.ts` | Apache-2.0 | Reference and test-vector source for deploy signing, the Web3 keystore and the HTTP client. | The parity script in `tests/parity/` is adapted from `keys.ts` and carries an attribution header. Apache-2.0 notices are retained; modifications are noted in the file. |
| [r-wallet](https://github.com/rhovision-org/r-wallet) | GPL-3.0 | Reference for wallet UX, the complete deploy encoder (`src/api/sign.ts`) and the MetaMask integration. No source is copied in this commit. | If code is copied later, the copied files keep a GPL-3.0 notice; GPL-3.0 code is not relicensed. See `book/src/guides/cli.md` for the MetaMask finding. |
| [rholang-wasm](https://github.com/rhovision-org/rholang-wasm) | Apache-2.0 | Toolchain template for Rust → wasm-bindgen → React/Vite. Not a dependency of the SDK or wallet. | Retain the notice if any configuration or template code is copied. |

Rust and npm dependencies carry their own licenses; `cargo deny` and the npm license check
in CI enforce the allowlist.

## Source offer

The web application's footer links to this repository. That link is the AGPL §13 source
offer for the client served over a network.
