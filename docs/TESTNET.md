# The rhobot public testnet

The r-cash platform is deployed from the same built terms that the devnet harness
exercises. The testnet is the rhobot network: four bonded validators on two 1 GB hosts,
an idle chain that produces a block when a deploy arrives, network id `testnet`, shard
`/root`.

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

## Operational notes measured on this network

- **The hosts are 1 GB each.** Continuous block production (or a burst of large deploys)
  can drive `mem_available_mb` to single digits and make the HTTP API time out. The
  operator's rule is an idle chain; space deploys out and watch
  `https://testnet.rhobot.net/health`.
- **Reads can lag writes.** After a deploy finalises, an `explore-deploy` read can still
  return an older state for a moment (the same race documented for REV balances). Poll,
  or verify a registration before depending on it.
- **Multi-register deploys can lose a write.** A deploy that registers several Root keys
  in parallel, or rapidly successive registrations, has been observed to return `true`
  for a register whose entry is later absent. `harness/install_testnet.py` therefore
  verifies each component by `Root.resolve` after installation; re-register any missing
  key one at a time and re-read until it persists.
- **Stale health.** `/health` is a snapshot refreshed every 60 s by the node hosts. If
  `ts` is old, `ok` is `false`, `nodes` is `0`, or `mem_available_mb` is tiny, the API is
  not usable; stop deploying rather than retrying.
- Deploys cost a fraction of a cent of test REV; the faucet's 0.3 REV covers a full
  install. The client's default phlo limit (1,000,000) is enough for every r-cash term.

## Current deployment

Installed on the chain at height ~1,100: Root, kernel, Bounds, Governor, the pure maths,
oracle registry/hub, currency registry and directory, asset resolver, transfer book,
pool template, market layer, and the account factory. Missing Root entries were
re-registered after the install's parallel writes were lost. The REV and TUSD feeds and
the TUSD stablecoin were not yet listed when the validator APIs stopped responding
(`health: ok false`, `nodes: 0`, `mem_available_mb: 16`); recovering the hosts is an
operator task.
