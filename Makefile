VENV := .venv
PY := $(VENV)/bin/python
# The upstream project is rholo. The old RCHAIN_RUST_DIR name is still accepted.
RHOLO_DIR ?= $(or $(RCHAIN_RUST_DIR),../rholo)
export RHOLO_DIR

.PHONY: venv image devnet down status keys build probes deploy logs clean demo client-test web-build check-languages test-wasm measure measure-check check-arch check-captures spec-check tla-check install-v3 unit-v3 unit-feed unit-hub unit-stablecoin unit-liquidation unit-interest unit-accounts unit-transfer unit-market unit-all

venv:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip -q install -r harness/requirements.txt

image:
	cd $(RHOLO_DIR) && tools/devnet.sh build

devnet:
	cd $(RHOLO_DIR) && tools/devnet.sh up --validators 1

down:
	cd $(RHOLO_DIR) && tools/devnet.sh down -v

status:
	@curl -s http://localhost:40403/api/v1/status | $(PY) -m json.tool || echo "devnet not running"

keys:
	$(PY) tools/keygen.py --out .devnet/keys.json --faucet

build:
	$(PY) tools/build_contracts.py

measure:
	$(PY) tools/measure_contracts.py

measure-check:
	$(PY) tools/measure_contracts.py --check

check-arch:
	$(PY) tools/check_arch.py --check

check-captures:
	$(PY) tools/check_captures.py --check

# Phase 1 gate: build drift, byte/depth budgets, catalogue and capture lint.
spec-check: build measure-check check-arch check-captures

# TLC is optional; the TLA+ files are specifications, not runtime dependencies.
tla-check:
	@if command -v tlc >/dev/null 2>&1; then \
	  mkdir -p /tmp/rcash-tlc; \
	  for cfg in spec/tla/*.cfg; do \
	    echo "== $$cfg"; \
	    tlc -metadir /tmp/rcash-tlc -config "$$cfg" "$${cfg%.cfg}.tla" || exit 1; \
	  done; \
	else \
	  echo "tlc not installed; skipping TLA+ check"; \
	fi

# v0.3 kernel installer and isolated component checks.
install-v3: build
	$(PY) harness/install_v3.py

unit-v3:
	$(VENV)/bin/python harness/unit_v3.py

unit-feed:
	$(VENV)/bin/python harness/unit_feed.py

unit-hub:
	$(VENV)/bin/python harness/unit_hub.py

unit-stablecoin:
	$(VENV)/bin/python harness/unit_stablecoin.py

unit-liquidation:
	$(VENV)/bin/python harness/unit_liquidation.py

unit-interest:
	$(PY) harness/unit_interest.py

unit-accounts:
	$(VENV)/bin/python harness/unit_accounts.py

unit-transfer:
	$(VENV)/bin/python harness/unit_transfer.py

unit-market:
	$(VENV)/bin/python harness/unit_market.py

unit-all: unit-v3 unit-feed unit-hub unit-stablecoin unit-liquidation unit-interest unit-accounts unit-transfer unit-market

probes: build
	$(PY) harness/rcash.py probes

deploy: build
	@test -n "$(FILE)" || (echo "usage: make deploy FILE=path/to.term.rho" && exit 1)
	$(PY) harness/rcash.py deploy "$(FILE)"

logs:
	cd $(RHOLO_DIR) && tools/devnet.sh logs devnet-bootstrap

clean:
	rm -rf contracts/build harness/__pycache__ tools/__pycache__

# The acceptance journey is the Rust client against the installed components.
# It assumes a running devnet with the components installed (`make install`).
demo:
	cargo run -p rcash-cli -- devnet demo

# The Python scenarios remain as the legacy harness for one release.
client-test:
	cargo test --workspace --exclude rcash-wasm

# The project is Rust, Rholang, Python and TypeScript. Reject native sources,
# native-compiling crates, native build tools and native artifacts.
check-languages:
	python3 tools/check_languages.py

# The wasm boundary is tested offline in Node.
test-wasm:
	cargo test -p rcash-wasm --features rcash-chain/native
	npm --prefix web run test:wasm

web-build:
	cd web && npm ci && npm run wasm:build && npm run typecheck && npm test && npm run build
