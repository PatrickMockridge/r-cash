# The rhobot public testnet

The r-cash platform is deployed from the same built terms that the devnet harness
exercises. The testnet is the rhobot network: four bonded validators on two **1 GB**
hosts, an idle chain that produces a block when a deploy arrives, network id `testnet`,
shard `/root`.

> **Hardware note.** The rholo node's advised memory is **8–16 GB**; these validators run
> on 1 GB each. The stalls, read lag, lost registrations and height divergence observed
> while deploying r-cash are consistent with resource exhaustion on hosts below the
> minimum advisory. They are **not** evidence about the protocol. Re-run the deploy on
> adequately provisioned nodes before drawing conclusions about node reliability.

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
