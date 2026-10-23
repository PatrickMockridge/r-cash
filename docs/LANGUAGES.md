# Language policy

R-Cash is written in **Rust, Rholang, Python and TypeScript**. There is no C or C++
source in this repository, and none is accepted. The same applies to the build: no
dependency, build script, tool or CI step may compile or invoke C/C++.

| Layer | Language | Path |
|---|---|---|
| Protocol contracts | Rholang | `contracts/` |
| Client SDK, CLI, WASM | Rust | `crates/` |
| Frontend | TypeScript + React | `web/` |
| Build tooling, legacy devnet harness | Python | `tools/`, `harness/` |

## The rule

1. No `.c`, `.cc`, `.cpp`, `.cxx`, `.h`, `.hh`, `.hpp`, `.hxx`, `.ino`, `.m`, `.mm`,
   `.asm`, `.S`, `CMakeLists.txt` or `.cmake` file may be added.
2. No crate in `Cargo.toml`/`Cargo.lock` may compile C/C++ or run a C/C++ tool. This
   bans `ring`, `cc`, `cmake`, `bindgen`, `minicov`, `aws-lc-*`, `openssl-sys`,
   `rchain-models` and native `*-sys` crates. `js-sys`, `web-sys` and `windows-sys` are
   Rust bindings, not native builds, and are allowed.
3. No build script, Makefile target, npm script, CI job or developer prerequisite may
   invoke `protoc`, `wasm-opt` (Binaryen), CMake, bindgen or a C/C++ compiler.
4. No native `.o`, `.a`, `.so`, `.dll`, `.dylib` or `.node` artifact may be committed.

Enforced by one command, locally and first in CI:

```sh
make check-no-cpp           # tools/check_no_cpp.py
```

`make check-languages` is kept as an alias. CI job: `languages` in
`.github/workflows/ci.yml`.

The Rust linker is not an exception to this rule: `rustc` uses the platform linker
(`cc`/`ld`) to produce native binaries. That is part of the Rust toolchain, not C/C++
code in this project. The guard checks the Cargo graph and build-script output for C/C++
*compilations*, not for rustc's link step.

## What was removed

The guard exists because "no `.cpp` files" was not enough:

| Removed | Why it was C/C++ | Replacement |
|---|---|---|
| `reqwest` `rustls-tls` → `ring` (C + assembly) and `cc` | TLS backend compiled C | Default-features-off `reqwest`; devnet uses HTTP. No TLS backend is linked. |
| `rchain-models` → `protoc` | Its build script ran the C++ protobuf compiler | A local prost `DeployData` in `crates/rcash-chain/src/deploy.rs` with the node's field tags; golden bytes pin parity. |
| `wasm-bindgen-test` → `minicov` | `minicov`'s build script compiles nine C files with `clang` | Host tests (`cargo test -p rcash-wasm --features rcash-chain/native`) plus the offline Node boundary test `web/tests/wasm-smoke.mjs`. |
| `wasm-pack` release → `wasm-opt` (Binaryen) | C++ optimizer run by wasm-pack | `[package.metadata.wasm-pack.profile.release] wasm-opt = false` in `crates/rcash-wasm/Cargo.toml`. The bundle is larger; correctness and the language rule win. |
| `protobuf-compiler` in CI | Installed `protoc`, no longer used | Deleted from all CI jobs and prerequisites. |

`wasm-bindgen` and `wasm-pack` themselves are Rust binaries and are allowed. `wasm-pack`
is configured never to fetch or execute Binaryen.

## What is not repository code

- The node checkout (`../RNodeRust`) is a separate upstream repository. It has two C
  audit shims under `spec/audit/evidence/` and Lean-generated `.c` files under
  `spec/.lake/`. R-Cash does not vendor, build or import them.
- `web/node_modules/` is npm output. Playwright vendors a C++-compiled WebP codec wasm
  there; it is gitignored, is not built by R-Cash and is not part of the application
  bundle. Removing it would mean dropping Playwright.
- System-wide `protoc`/Binaryen installations are irrelevant: the guard and the CI shims
  prove no project build path invokes them.

## Measured inventory (2026-10-23)

```sh
git ls-files | grep -Ei '\.(c|cc|cpp|cxx|h|hh|hpp|hxx|ino|m|mm|asm)$|\.S$|(^|/)CMakeLists\.txt$|\.cmake$'
# no output
python3 tools/check_no_cpp.py
# no-cpp: clean (... host and wasm graphs; lockfile; tool scripts)
```

The repository contains 0 C/C++ files, 0 CMake files, and 0 C/C++-compiling crates on
the host or wasm32 graph.
