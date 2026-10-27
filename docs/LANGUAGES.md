# Languages

R-Cash is written in **Rust, Rholang, Python and TypeScript**, with formal
specifications in **TLA+ and Lean 4**.

| Layer | Language | Path |
|---|---|---|
| Protocol contracts | Rholang | `contracts/` |
| Client SDK, CLI, WASM | Rust | `crates/` |
| Frontend | TypeScript + React | `web/` |
| Build tooling, legacy devnet harness | Python | `tools/`, `harness/` |
| Concurrency specifications | TLA+ | `spec/tla/` |
| Transition and arithmetic proofs | Lean 4 | `spec/lean/` |

Rholang library includes use the `.rho` extension. `tools/build_contracts.py` assembles
them into deployable terms under `contracts/build/` through `@@INLINE:...@@` markers. The
v0.3 core does not inline stateful components; see `docs/spec/`.

TLA+ is a specification language only. The files under `spec/tla/` are not compiled,
packaged or run by the application; `make tla-check` runs the model checker when it is
available and otherwise skips it.

Lean 4 is a specification and proof language only. The project under `spec/lean/` is
pinned by `lean-toolchain`, has no Mathlib dependency and is never imported by the
application. `make lean-check` builds it, rejects `sorry`/`admit`/`native_decide` and
audits the axioms of every main theorem. Lean models the transition relation, the
arithmetic and the linear-cell discipline; it does not formalise Rholang syntax. The
flow specification in `docs/spec/flows/` maps each contract arm to a model transition.

The language check is:

```sh
make check-languages
```
