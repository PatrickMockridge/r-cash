# The public testnet

The rholo public testnet is a disposable, no-value network. It may be reset at any time. The
campaign tooling pins the network identity and refuses to continue if it changes. This chapter
describes the current testnet and the campaign procedure, and records the one campaign that
was blocked.

## Current identity

| | |
|---|---|
| Network id | `testnet` |
| Shard id | `/testnet` |
| Genesis block 0 | `133b1d307b1750129cf0cfb69c4c8f950da21c4e8db2a6a076464d0ccfd98d44` (rebuilt 2026-10-29) |
| Public HTTP (nginx → validator A) | `https://testnet.rhobot.net` |
| Direct HTTP A / B | `http://164.90.140.144:40403`, `http://167.99.43.214:40403` |
| Health | `https://testnet.rhobot.net/health` |
| Faucet | `POST /api/faucet` (also `/api/v1/faucet`) — 0.3 REV per drip; the live faucet funds an address once, and the tooling caps at ten drips per address per process; 429 when rapid |
| Chain | Idle: no autopropose, `proposeOnDeploy=true`; a block appears when a deploy arrives |
| Finality | More than 2/3 of the 1,000-stake pool; one validator down keeps finality, two stop it |

The 2026-10-29 rebuild replaced the chain and the binary. **Old manifests and keys are
invalid.** Do not resume a stale campaign or reuse an old URI manifest.

At the time of the rebuild the node reported: `rholo node 0.1.0
(d1af45d1db3f5fe2fa6047ad6c8a72b654d041df)`, height 6, `minPhloPrice=1`, `devMode=true`,
`acceptsDeploys=true`, 23 nodes.

The native reqwest client has no TLS backend. Use a direct HTTP validator for CLI/SDK writes.
Browsers and the web/WASM client use `https://testnet.rhobot.net` (CORS is `*`).

The current pinned binary predates the deploy hostlist: `GET /api/v1/nodes` returns 404, so
the client uses its configured seed alone. Discovery is feature-detected; the CLI/SDK begin
verifying and spreading reads automatically once a hostlist-enabled binary is pinned. Each
signed deploy still goes to exactly one node and is never re-submitted elsewhere. Until then
the harness passes the profile's known validators (`httpFallbacks`) to the CLI as `--nodes`, so
its deploys still spread over the validators and its reads fail over on 503/transport errors.
Browsers on
the HTTPS endpoint cannot use the hostlist's `http://ip:40403` entries (mixed content) and
keep their HTTPS seed.

## Campaign setup

```sh
# read-only identity, safety and key preflight
make testnet-preflight

# fresh random keys, 0600 under .testnet/; never the devnet deployer
make testnet-keys

# faucet drips, ledger and native-REV consolidation
make testnet-fund

# isolated platform install (17 steps), then feeds + TUSD listing
make testnet-install
make testnet-setup
```

`testnet-install` deploys with shard `/testnet`, phlo 2,000,000 / price 1 and
`--min-lock-blocks 10`, then verifies every component with a signed `Root.resolve`. The
generated manifest is `.testnet/testnet-v4.json`; it contains public URIs only.
`deployments/*.json` and `.testnet/` are gitignored.

All testnet commands are opt-in and require `--allow-live`. They read
`configs/testnet.json`. Keys are generated fresh under `.testnet/` with mode 0600; the devnet
deployer is never reused.

## Campaign stages

```sh
make testnet-core        # 14 suites, ticker running for the idle chain
make testnet-mesh        # 16 native currencies, 24 priority pairs
make testnet-unit-mesh   # reverse lookup, guard order, pauseAsset
make testnet-clients     # CLI reads against the public chain
make testnet-demo        # end-to-end send/claim
```

`make testnet-campaign` runs them in order with the preflight, funding and
stop-on-first-failure gates. A failure is classified model/spec, refinement, fixture or
platform; the campaign is not silently resumed.

## Chain behaviour that changes the tests

- **Idle blocks.** `unit_timelock` and any explicit height wait need the ticker
  (`harness/ticker.py`); the suites' own deploys also advance height.
- **Faucet rate.** A drip is a deploy that must be finalized before the balance moves. The live
  faucet funds an address once; a second request is refused. The funder uses a per-address
  ledger, honours 429/Retry-After and caps at ten drips per address per process. If the faucet
  cannot fund a stage, the campaign stops with the computed deficit.
- **Reset.** A rebuild changes genesis and invalidates every local URI. The preflight pins
  block 0; a mismatch aborts and requires a new campaign and fresh addresses.
- **Funding scale.** The public faucet cannot fund the mesh at the devnet REV price. The
  testnet mesh profile (`configs/mesh-testnet.json`) sets the REV reference price to \$100, so
  24 pairs cost about 4.3 REV of collateral instead of about 4,300. This changes the price
  level only; the contract arithmetic, pair topology and assertions are unchanged. Economic
  realism remains the devnet campaign at the production price.

## The 2026-10-28 campaign: BLOCKED

The campaign ran on the pre-rebuild chain. The isolated install, feeds and TUSD listing
passed. It then stopped when the testnet entered a resource-admission throttle and refused all
deploy and explore work:

```json
{"degraded":"throttled","acceptsDeploys":false,"latestBlockNumber":1688}
```

The node reported `mem_available_mb: 547` and returned 503:

```
503: resource state throttled: headroom below the throttle floor
(547 MiB available); new deploy and explore work is refused
while the node is throttled
```

The hosts were below the node's documented minimum. No contract, genesis or consensus change
was made; no assertion was weakened. The block is classified as a platform/operator problem,
not a contract result. The chain was later rebuilt (2026-10-29), which invalidated that
campaign's keys and manifests.

## What the testnet is for

The testnet is a rehearsal for the campaign, not a production service. It exercises:

- the 17-step install against a live network;
- the discovery and funding paths with a real faucet;
- the behavioural suites and the mesh on a chain with latency and multiple validators;
- the client reads and the send/claim demo.

It is not an economic test. The REV price is set for funding convenience, not realism. It is
not a security test. It is not an audit.

## Safety rules

- Never reuse devnet keys on the testnet.
- Never run a testnet command without `--allow-live`.
- Do not retry a value-moving deploy blindly. Use the op cache or a new operation id.
- Do not resume a campaign after a genesis change; generate fresh keys and a new manifest.
- Do not treat a blocked stage as a pass. A BLOCKED result is not conformance.

> **Where to go deeper.** The pinned operational config is `configs/testnet.json`; the mesh
> profile is `configs/mesh-testnet.json`. The installer is
> `harness/install_testnet.py`, and the funding/preflight tools are
> `harness/testnet_fund.py` and `harness/testnet_preflight.py`.
