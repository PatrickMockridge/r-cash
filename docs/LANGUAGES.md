# Language policy

R-Cash is written in **Rust, Rholang, Python and TypeScript**. There is no C or C++
source in this repository, and none is accepted.

| Layer | Language | Path |
|---|---|---|
| Protocol contracts | Rholang | `contracts/` |
| Client SDK, CLI, WASM | Rust | `crates/` |
| Frontend | TypeScript + React | `web/` |
| Build tooling, legacy devnet harness | Python | `tools/`, `harness/` |

## The rule

No `.c`, `.cc`, `.cpp`, `.cxx`, `.h`, `.hh`, `.hpp`, `.hxx`, `.ino`, `CMakeLists.txt`
or `.cmake` file may be added. No build step may compile C or C++.

Enforced in two places:

```sh
make check-languages                 # local
.github/workflows/ci.yml             # the `languages` job
```

The check is an allowlist at the file level: it fails on the extensions above, so a
native component cannot arrive unnoticed behind a build script.

## Why

- **One signing and encoding implementation.** The same Rust code signs in the CLI, the
  SDK and the browser WASM module. A second language would mean a second protobuf
  encoder and a second ECDSA path, which is exactly where deploy-parity bugs live.
- **The North Star is WASM from Rust.** A C++ client cannot share the SDK; it would
  need bindings and a parallel test suite.
- **Auditability.** The R0a gate pins byte-identical output across Rust native, wasm32 and
  an independent TypeScript signer. Adding a compiled native layer widens that surface.

## What is not repository code

Prebuilt toolchain binaries are not sources and are allowed: `protoc` (protobuf codegen),
`wasm-opt` (Binaryen, invoked by `wasm-pack`), `wasm-bindgen`, and the Docker image. They
are pinned by the documented toolchain and never vendored into this repository.

The node itself (`../RNodeRust`) is Rust and contains no C++ sources. Its two C files under
`spec/audit/evidence/` are audit instrumentation for the node, not part of R-Cash, and are
not imported here. Lean-generated `.c` files under `spec/.lake/` are build output.

## Measured inventory (2026-10-23)

```sh
git ls-files | grep -Ei '\.(c|cc|cpp|cxx|h|hh|hpp|hxx|ino)$|(^|/)CMakeLists\.txt$|\.cmake$'
# no output
```

At the time of writing the repository contains 0 C/C++ files and 0 CMake files.
