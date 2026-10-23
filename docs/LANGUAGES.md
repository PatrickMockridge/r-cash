# Languages

R-Cash is written in **Rust, Rholang, Python and TypeScript**.

| Layer | Language | Path |
|---|---|---|
| Protocol contracts | Rholang | `contracts/` |
| Client SDK, CLI, WASM | Rust | `crates/` |
| Frontend | TypeScript + React | `web/` |
| Build tooling, legacy devnet harness | Python | `tools/`, `harness/` |

Rholang library includes use the `.rho` extension. `tools/build_contracts.py` assembles
them into deployable terms under `contracts/build/` through `@@INLINE:...@@` markers.

The language check is:

```sh
make check-languages
```
