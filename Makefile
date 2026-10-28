VENV := .venv
PY := $(VENV)/bin/python
# The upstream project is rholo. The old RCHAIN_RUST_DIR name is still accepted.
RHOLO_DIR ?= $(or $(RCHAIN_RUST_DIR),../rholo)
export RHOLO_DIR

.PHONY: venv image devnet down status keys build probes deploy logs clean demo client-test web-build check-languages inventory flows check-flows check-trace check-mesh vectors-check model-test offline-test pre-devnet-check lean-build lean-check formal-check mesh-plan mesh-install mesh-pair test-wasm measure measure-check check-arch check-captures spec-check tla-check install install-v3 bootstrap setup unit-v3 unit-feed unit-hub unit-stablecoin unit-liquidation unit-interest unit-savings unit-psm unit-timelock unit-accounts unit-transfer unit-transfer-memo unit-market unit-mesh unit-external unit-buffer unit-pool unit-all

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

# v0.4 kernel installer and isolated component checks.
install-v3: build
	$(PY) harness/install_v3.py

# The chain-aware installer used for fresh campaigns (signed-read verification).
# The defaults point at the public-testnet key/state paths, so the devnet run must
# pass every path explicitly.
install: build
	$(PY) harness/install_testnet.py --node http://localhost:40403 \
	  --keys .devnet/keys.json --admin-keys .devnet/keys.json \
	  --ops .devnet/ops --state .devnet/v3-install.json \
	  --manifest deployments/devnet-v4.json --min-lock-blocks 10 --fresh

# Bootstrap the demo system and market through the acceptance suites; systems are
# discovered by clients through ListingViews, so no separate systems manifest is
# required.
bootstrap: unit-stablecoin unit-market

# One command from an empty host to a bootstrapped devnet.
setup: devnet keys install bootstrap

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

unit-savings:
	$(PY) harness/unit_savings.py

unit-psm:
	$(PY) harness/unit_psm.py

unit-timelock:
	$(PY) harness/unit_timelock.py

# The buffer checks (sin, mint halt, cover waterfall) are part of the liquidation
# suite; these aliases name the specification areas for the campaign report.
unit-buffer: unit-liquidation

unit-pool: unit-market

unit-accounts:
	$(VENV)/bin/python harness/unit_accounts.py

unit-transfer:
	$(VENV)/bin/python harness/unit_transfer.py

unit-transfer-memo:
	$(PY) harness/unit_transfer_memo.py

unit-market:
	$(VENV)/bin/python harness/unit_market.py

unit-mesh:
	$(VENV)/bin/python harness/unit_mesh.py

unit-external:
	$(VENV)/bin/python harness/unit_external.py

unit-all: unit-v3 unit-feed unit-hub unit-stablecoin unit-interest unit-liquidation unit-savings unit-psm unit-timelock unit-accounts unit-transfer unit-transfer-memo unit-market unit-mesh unit-external

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
	cargo run -p rcash-cli -- --key deployer devnet demo

# The Python scenarios remain as the legacy harness for one release.
client-test:
	cargo test --workspace --exclude rcash-wasm


# Formal programme: the flow YAML and the Lean model are authoritative.
inventory:
	$(PY) tools/rho_inventory.py --write

flows:
	$(PY) tools/render_flows.py

check-flows:
	$(PY) tools/rho_inventory.py --check
	$(PY) tools/check_flows.py --check --strict
	$(PY) tools/render_flows.py --check

check-trace:
	$(PY) tools/check_traceability.py --check --strict

check-mesh:
	$(PY) tools/check_mesh.py

vectors-check:
	$(PY) tools/check_vectors.py

model-test:
	$(PY) -m unittest discover -s tests/model -t tests/model

offline-test: vectors-check model-test client-test test-wasm web-build

pre-devnet-check: spec-check formal-check vectors-check model-test check-languages
	cargo fmt --all -- --check
	cargo clippy --workspace --exclude rcash-wasm --all-targets -- -D warnings
	cargo test --workspace --exclude rcash-wasm
	cargo check -p rcash-wasm --target wasm32-unknown-unknown
	cargo test -p rcash-wasm --features rcash-chain/native
	npm --prefix web run typecheck
	npm --prefix web test

lean-build:
	cd spec/lean && lake build

lean-check:
	$(PY) tools/check_lean.py

formal-check: lean-check check-flows check-trace check-mesh

# The tracked mesh config is the source for the supported currency set.
mesh-plan:
	$(PY) tools/mesh.py --config configs/mesh.json plan

mesh-install:
	$(PY) tools/mesh.py --config configs/mesh.json install

mesh-pair:
	$(PY) tools/mesh.py --config configs/mesh.json pair $(BASE) $(QUOTE)

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
