# TLA+ models

These finite models encode the safety properties of the v0.3 component calculus. They are
specifications, not runtime code. The model checker (TLC) is optional and is not part of the
required build; `make tla-check` runs it when it is on `PATH`.

| Model | Property |
|---|---|
| `CellLinearity.tla` | one holder at a time; quiescent cell is `Full`; a holder sees `Empty` |
| `TransferExclusivity.tla` | open ⇒ payment held; terminal ⇒ payment gone; at most one terminal transition |
| `PoolConservation.tla` | reserves equal custody; `totalShares = minted − burned` |
| `CapabilityProvenance.tla` | a caller-supplied capability never enters authoritative storage |
| `AdminNonce.tla` | no nonce replay; every executed nonce is at or below the governor nonce |

Each `.tla` has a `.cfg` with the invariants TLC should check. The models use small bounded
domains (2 actors, 2 transfers, reserves up to 12) so TLC terminates.

## Installing TLC

TLC is distributed as `tla2tools.jar`. It is an optional workstation tool, not a
build or runtime dependency of R-Cash.

```sh
mkdir -p ~/.local/share/tlaplus ~/.local/bin
curl -L -o ~/.local/share/tlaplus/tla2tools.jar \
  https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar
cat > ~/.local/bin/tlc <<'EOF'
#!/usr/bin/env sh
exec java -cp "$HOME/.local/share/tlaplus/tla2tools.jar" tlc2.TLC "$@"
EOF
chmod +x ~/.local/bin/tlc
```

Ensure `~/.local/bin` is on `PATH`, then run one model:

```sh
tlc -metadir /tmp/rcash-tlc \
  -config spec/tla/PoolConservation.cfg spec/tla/PoolConservation.tla
```

Run all models:

```sh
make tla-check
```

All five models were checked with TLC 2.19 (tla2tools 1.7.4) on 2026-10-23:
`AdminNonce` 64 states, `CapabilityProvenance` 13, `CellLinearity` 5,
`PoolConservation` 60586, `TransferExclusivity` 13. The finite bounds are
deliberately small; the models check the protocol shape, not production-scale
state spaces. The v0.4 stablecoin issuer model is added with the issuer in Phase 1.

The models are abstractions. They do not model phlo, the node scheduler or the Rholang
parser; those are covered by `tools/measure_contracts.py` and the devnet scenarios.
