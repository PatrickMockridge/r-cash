VENV := .venv
PY := $(VENV)/bin/python
RCHAIN_RUST_DIR ?= ../RNodeRust
export RCHAIN_RUST_DIR

.PHONY: venv image devnet down status keys build probes deploy logs clean bootstrap pool book demo legacy-demo client-test web-build check-languages

venv:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip -q install -r harness/requirements.txt

image:
	cd $(RCHAIN_RUST_DIR) && tools/devnet.sh build

devnet:
	cd $(RCHAIN_RUST_DIR) && tools/devnet.sh up --validators 1

down:
	cd $(RCHAIN_RUST_DIR) && tools/devnet.sh down -v

status:
	@curl -s http://localhost:40403/api/v1/status | $(PY) -m json.tool || echo "devnet not running"

keys:
	$(PY) tools/keygen.py --out .devnet/keys.json --faucet

build:
	$(PY) tools/build_contracts.py

probes: build
	$(PY) harness/rcash.py probes

deploy: build
	@test -n "$(FILE)" || (echo "usage: make deploy FILE=path/to.term.rho" && exit 1)
	$(PY) harness/rcash.py deploy "$(FILE)"

logs:
	cd $(RCHAIN_RUST_DIR) && tools/devnet.sh logs devnet-bootstrap

clean:
	rm -rf contracts/build harness/__pycache__ tools/__pycache__

bootstrap: build
	$(PY) harness/bootstrap.py

pool: bootstrap
	$(PY) harness/pool_bootstrap.py

book: pool
	$(PY) harness/transfer_bootstrap.py

# The acceptance journey is the Rust client against the installed components.
# It assumes a running devnet with the components installed (`make install`).
demo:
	cargo run -p rcash-cli -- devnet demo

# The Python scenarios remain as the legacy harness for one release.
legacy-demo: book
	$(PY) harness/scenarios/pool.py
	$(PY) harness/scenarios/transfer.py

client-test:
	cargo test --workspace --exclude rcash-wasm

# The project is Rust, Rholang, Python and TypeScript. Reject native C/C++ sources.
check-languages:
	@if git ls-files | grep -Eiq '(\.(c|cc|cpp|cxx|h|hh|hpp|hxx|ino)|(^|/)CMakeLists\.txt|\.cmake)$$'; then \
		echo "error: C/C++ sources are not allowed; see docs/LANGUAGES.md"; \
		git ls-files | grep -Ei '(\.(c|cc|cpp|cxx|h|hh|hpp|hxx|ino)|(^|/)CMakeLists\.txt|\.cmake)$$'; \
		exit 1; \
	else \
		echo "languages: no C/C++ sources"; \
	fi

web-build:
	cd web && npm ci && npm run wasm:build && npm run typecheck && npm test && npm run build
