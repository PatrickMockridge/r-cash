# Campaign report — 2026-10-27

**Verdict: 13/13 devnet suites and the CLI demo pass on a fresh fixed-node devnet,
after `make formal-check` and `make spec-check` are green.**

## Environment

- Fixed rholo node (`/home/patrick/rholo-fixed`), one validator, autopropose and
  admin propose enabled, disposable devnet (`make down` then `make devnet`).
- One install (`make install --fresh`), no contract changes after the install.
- One pass per suite, in the order below, on the same chain.

## Results

| suite | result |
|---|---|
| unit-v3 | pass |
| unit-feed | pass |
| unit-hub | pass |
| unit-stablecoin | pass |
| unit-interest | pass |
| unit-liquidation | pass |
| unit-savings | pass |
| unit-psm | pass |
| unit-timelock | pass |
| unit-accounts | pass |
| unit-transfer | pass |
| unit-transfer-memo | pass |
| unit-market | pass |
| `make demo` | pass (`claimedBaseUnits: 101000000`) |

## Defects reconciled before the campaign

| ID | fix |
|---|---|
| D2.1 | `vaultMintCommit` reposts `vaultState` before the `recapitalise` refusal |
| D2.2 | `applyPolicy` reposts `psmState` before the `ceiling` refusal |
| D1.1 | `setPaused` no longer posts the peeked `currencyState` on the no-currency branch |
| D5.1 | dead outer `TransferContract` binder removed |
| L1 | `LiquidityLock.fund` reads `poolNow` and refuses `lock too short` below `now + lockMinBlocks` |
| P1 | `sellStable` enforces `stableDebt - amount + maxSupply >= 0` and refuses `psm floor` |
| Cover D1 | the buffer-payment branch of `cover` no longer posts the peeked cell |
| R1 | §18.3 regenerated from the deploy inventory; every reason is canonical |

The cover duplicate was found by `tools/check_flows.py`, not by the campaign.

## Harness corrections made during the campaign

These are fixture changes, not contract changes:

- fund the sponsor before feed binding and market creation; fund `ramp` in the
  account suite;
- retry a rate-limited faucet drip instead of silently leaving a later key
  unfunded;
- accelerate block waits through the devnet admin propose endpoint;
- widen the transfer expiry window and the market lock window;
- make the liquidation interest-only repay use the vault's actual accrued
  interest, and allow a per-run currency suffix for re-runs;
- run `make demo` with the funded `deployer` key.

## Residual assumptions

- Native ERTP/REV behaviour, Rholang integer division and deploy atomicity are
  platform assumptions; the campaign is the only check of them.
- The flow/Lean bridge is the generated arm inventory, the source-derived
  access/refusal checks and the per-arm effect map. Peripheral Lean modules are
  transition models; the core arithmetic, cell discipline and S1–S3/S9–S12
  obligations carry proofs.
- S4–S7 are transition obligations, not untimed state predicates.
