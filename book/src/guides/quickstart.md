# Quickstart on the devnet

The local devnet is the supported environment for running R-Cash end to end. This guide takes
a fresh host to a bootstrapped chain and a send → claim demo. It assumes you are in the
repository root.

## Prerequisites

- Docker, with enough memory for the node container (the devnet is happiest with several GB).
- Python 3.12.
- Node 22 and npm.
- A checkout of [rholo](https://github.com/rhovision-org/rholo). Set `RHOLO_DIR`; it defaults
  to `../rholo`.
- Rust 1.95.0 or the toolchain pinned by `rust-toolchain.toml` if you want to build the CLI.

The devnet node is built from the rholo checkout. The first build is slow; subsequent runs
reuse the image.

## The short path

```sh
make venv     # .venv + Python harness dependencies
make image    # build rnode:local from RHOLO_DIR (once; slow)
make setup    # devnet + keys + install + bootstrap
make probes   # phase-0 capability gates
make demo     # Rust client send -> claim journey
make down     # stop and remove the devnet
```

`make setup` chains four steps:

1. `make devnet` starts a one-validator node with the public HTTP API on port 40403.
2. `make keys` creates the devnet keystore in `.devnet/keys.json` and funds the deployer.
3. `make install` runs the chain-aware installer: 17 steps, each with a signed read
   verification, writing `deployments/devnet-v4.json` only after every step resolves.
4. `make bootstrap` runs the stablecoin and market acceptance suites, leaving a demo currency
   system and a market on chain.

## What each command does

### `make venv`

Creates `.venv` and installs `harness/requirements.txt`. The harness is the Python tooling
that drives the node, funds keys and runs the behavioural suites. It is build-time and
operational tooling, not part of the protocol.

### `make image`

Builds the rholo node image from `RHOLO_DIR`. The image is tagged `rnode:local`. This is the
one slow step; it compiles the node.

### `make devnet`

Starts the container with one validator. The public HTTP API is on `http://localhost:40403`;
the admin API is on 40405; deploy gRPC is 40402. The node is a development chain with a
faucet and `devMode`.

### `make keys`

Generates the devnet keys. The deployer is validator 0 and is funded at genesis. The command
is idempotent: it reuses an existing keystore unless `--fresh` is passed. Do not reuse devnet
keys on a public chain.

### `make install`

Runs `harness/install_testnet.py` against the devnet. Every step has an operation id and a
cached signed body, so a transport retry reuses the exact bytes. A step is verified at the
block that carried it: the deploy is not in `rejectedDeploys`, and every expected `Root` key
resolves at that block's post-state. The manifest is written only after the final step.

### `make bootstrap`

Deploys the demo currencies, feeds and market through the acceptance suites. Systems and
markets are discovered through `ListingViews`; there is no separate systems manifest.

### `make probes`

Runs the phase-0 capability gates: ERTP, REV, the Rholang parser, deploy atomicity, finality
and the measured platform limits. These are the assumptions the contracts rely on.

### `make demo`

Builds the CLI and runs:

```
rcash devnet demo
```

The journey funds the account, sends a claimable native-REV transfer to itself, and claims it.
It is a smoke journey, not the full acceptance campaign.

## What you should see

A successful `make setup` ends with a manifest at `deployments/devnet-v4.json` and a chain
that answers:

```sh
curl -s http://localhost:40403/api/v1/status
```

The status response includes `latestBlockNumber`, `minPhloPrice` and the shard. The devnet
shard is `/root`; `root` is rejected.

A successful `make demo` prints the transfer id, the claim fragment and a claimed balance.
The exact numbers depend on the faucet and the demo amount.

## Common failures

| Symptom | Likely cause | What to do |
|---|---|---|
| `Deploy shardId 'root' is not a member...` | Used `root` instead of `/root` | Set the shard to `/root` |
| A deploy is accepted but never proposed | `validAfterBlockNumber` anchored at 0 | Let the client anchor at the current tip |
| `stale feed` on mint or swap | Devnet feeds are older than the bound | Refresh the feeds with `harness/feed_refresh.py` or re-run bootstrap |
| `pool.quote` refuses | You used `explore-deploy`, which has no block context | Use a signed read |
| The node container is killed | Host memory below the node's needs | Give Docker more memory; the testnet history shows what happens below the minimum |
| `make install` fails partway | A step did not resolve | Re-run; the op cache makes retries safe. Do not hand-edit the manifest |
| The web app cannot find a manifest | `web/scripts/sync-manifest.mjs` has not run | `npm run dev` runs it in `predev` |

## Next steps

- [The CLI](cli.md) — the full command surface, including the `v4` reads and writes.
- [The web app](web-app.md) — the browser journey.
- [The public testnet](testnet.md) — what changes on a live, disposable chain.
- [Testing and the acceptance campaign](../trust/testing.md) — how to run the suites yourself.

> **Where to go deeper.** The platform limits and measured costs that shape these commands are
> in [Repository and implementation map](../trust/repository-map.md). The install order is in
> [`docs/spec/30-WIRING.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/30-WIRING.md).
