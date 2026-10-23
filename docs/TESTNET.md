# The rhobot public testnet

The r-cash platform is deployed from the same built terms that the devnet harness
exercises. The testnet is the rhobot network: four bonded validators on two **1 GB**
hosts, an idle chain that produces a block when a deploy arrives, network id `testnet`,
shard `/root`.

> **Hardware note.** The rholo node's advised memory is **8–16 GB**; these validators run
> on 1 GB each. The stalls, read lag, lost registrations and height divergence observed
> while deploying r-cash are consistent with resource exhaustion on hosts below the
> minimum advisory. They are **not** evidence about the protocol. **Restarting the units
> does not remedy this**: on 1 GB the same collapse returns under any real deploy load.
> The hosts must be resized to at least 8 GB (16 GB+ to be comfortable) before the
> network is usable for a production-shaped workload.

| | |
|---|---|
| Endpoint | `https://testnet.rhobot.net` (nginx → validator A's HTTP API) |
| Direct validators | A `164.90.140.144:40403`, D `164.90.140.144:41403`, B `104.131.176.164:40403`, C `104.131.176.164:41403` |
| Health | `https://testnet.rhobot.net/health` (a 60 s snapshot, not a live API) |
| Faucet | `POST /api/faucet {"address": "..."}` — 0.3 REV per drip, ten drips per address per process |

The node operator's own documentation is in the rholo repository
(`docs/src/node/testnet.md`): genesis, wallets, ports, recovery and the measured
failover behaviour.

## Deploying r-cash

```sh
# a key on the testnet; the faucet funds it, then it pays every deploy
cargo run -p rcash-cli -- --keys .testnet/keys.json keygen --out .testnet/keys.json --names deployer
# POST the address to the faucet, poll /api/v1/deploy-status/<deployId> until success

python3 harness/install_testnet.py            # kernel, registries, market, accounts
python3 harness/testnet_setup.py             # REV/TUSD feeds, TUSD stablecoin, listing
```

The installer renders the same terms as `harness/install_v3.py` and deploys them with
`target/debug/rcash deploy` against the testnet HTTP API. It writes
`deployments/testnet-v4.json` and local state in `.testnet/install.json`; both are
generated and `.testnet/` holds the key, so neither is committed.

Use `--node` to pick a validator. The direct HTTP ports avoid the node CLI's missing TLS
backend; `https://testnet.rhobot.net` works for curl and browsers but not the native
client.

## Operating on an under-provisioned chain

Everything below was observed on the 1 GB hosts and should be read as symptoms of memory
pressure, not as node bugs:

- **`mem_available_mb` collapses to single digits** under a burst of deploys; the HTTP API
  then times out. Space deploys out and watch `https://testnet.rhobot.net/health`.
- **Reads can lag writes** while the node is under load. Poll or re-read rather than
  trusting the first response.
- **A multi-key Root registration can report success for an entry that is later absent.**
  `harness/install_testnet.py` verifies every component with `Root.resolve` and
  re-registers missing keys one at a time. This is defensive tooling; it is not a claim
  that Root loses writes on adequate hardware.
- **Health is a 60 s snapshot.** An old `ts`, `ok: false`, `nodes: 0` or tiny memory means
  the API is not usable; stop deploying rather than retrying.
- Deploys cost a fraction of test REV; the faucet's 0.3 REV covers a full install and the
  client's default phlo limit (1,000,000) is enough for every r-cash term.

## Current deployment

The platform terms were deployed at height ~1,100 against validator A. Registrations
were then verified and repaired through `Root.resolve`. The REV and TUSD feeds and the
TUSD stablecoin were not completed: the hosts ran out of memory and the validator APIs
stopped responding. This run says the hosts are below the advised minimum; it does not
test the protocol beyond the deploy acceptance it already demonstrated. A re-run on
8–16 GB nodes is the correct next experiment.

## Joining as an observer from an adequately provisioned host

An observer syncs and serves the API but does not vote, so it helps with reads and
deploy submission rather than with the validators' quorum. It runs the same binary the
network does (`71c6a513d`, the version `/api/status` reports).

```sh
git -C ../rholo worktree add --detach /tmp/rholo-71c6 71c6a513d
CARGO_TARGET_DIR=/tmp/rholo-target cargo build --release -p rchain-node --bin rnode

rnode run --data-dir ~/.rnode-observer \
  --host 127.0.0.1 --api-host 127.0.0.1 --no-upnp \
  --network-id testnet --parent-shard-id / --shard-name root \
  --protocol-port 42400 --discovery-port 42404 \
  --api-port-grpc-external 42401 --api-port-grpc-internal 42402 \
  --api-port-http 42403 --api-port-admin-http 42405 \
  --bonds-file ~/.rnode-observer/genesis/bonds.txt \
  --wallets-file ~/.rnode-observer/genesis/wallets.txt \
  --pos-multi-sig-public-keys 042d721140c51d83d87503d86fa85e0c835c1b80dcb086251b7c59da497c6ed508625a5c0624741278af944e74f701e4d0f5c2b447b561a1e52f164e895c24b15d \
  --pos-multi-sig-quorum 1 \
  --bond-minimum 1 --bond-maximum 250 --number-of-active-validators 4 \
  --epoch-length 10 --quarantine-length 10 \
  --bootstrap "rnode://<validator-node-id>@<validator-host>?protocol=<port>&discovery=<port>" \
  --no-attest-on-new-blocks
```

The genesis files are network configuration, not ceremony: a joining node replays the
genesis and must produce the same post-state hash, so both files must match the chain.
The testnet's four bonds are the validators at 250 each; the four wallets are the
`alice`, `bob`, `carol` and `dave` addresses at 1,000,000,000,000 drops each, and
`--pos-multi-sig-public-keys` is dave's key (the trusted admission key). The genesis hash
the node must reproduce is `713c0ebb0eb4ce866ae118aa1177a498b4edb2d431dd8b77d28abcdd4da9ea91`.

Observed on 2026-10-23 while the validators were memory-starved:

- validators A and D timed out at the protocol handshake (`Failed to send
  FinalizedFringeRequest ... TimeOut`);
- B and C accepted the request but never answered it; the observer stayed at height 0
  with `peers: 1`.

That is consistent with the validator side of the fringe handler having nothing to
answer with while the chain's finality is degraded. **The fix is a host resize to the
advised 8–16 GB, not a restart**: a 1 GB validator returns to the same state under load.
After the resize and restart, the observer's retry loop restores the approved fringe, and
`127.0.0.1:42403` becomes a healthy API for the deploy tooling.
