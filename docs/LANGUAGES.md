# Languages

R-Cash is written in **Rust, Rholang, Python and TypeScript**.

| Layer | Language | Path |
|---|---|---|
| Protocol contracts | Rholang | `contracts/` |
| Client SDK, CLI, WASM | Rust | `crates/` |
| Frontend | TypeScript + React | `web/` |
| Build tooling, legacy devnet harness | Python | `tools/`, `harness/` |
| Formal specifications | TLA+ | `spec/tla/` |

Rholang library includes use the `.rho` extension. `tools/build_contracts.py` assembles
them into deployable terms under `contracts/build/` through `@@INLINE:...@@` markers. The
v0.3 core does not inline stateful components; see `docs/spec/`.

TLA+ is a specification language only. The files under `spec/tla/` are not compiled,
packaged or run by the application; `make tla-check` runs the model checker when it is
available and otherwise skips it.

The language check is:

```sh
make check-languages
```
