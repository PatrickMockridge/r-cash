# Status, scope and honest limits

A documentation rewrite is only useful if it tells the truth about what exists. This chapter
separates what is implemented, what has been verified, what is blocked and what was never
attempted. Dates are included because the repository moves.

## The short version

R-Cash is a **v0.5, devnet-only prototype**. It is not safe for real funds. The rholo chain is
pre-testnet, there has been no external audit, and no mainnet deployment exists.

| Claim | Evidence | Date |
|---|---|---|
| Contracts, clients and web UI implemented | Source tree and component catalogue | v0.5 |
| Static gates green | `make spec-check`, `make formal-check`, Rust/CI gates | 2026-10-27 onward |
| 13 behavioural suites + CLI demo passed on a fresh devnet | [`docs/spec/flows/CAMPAIGN.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/flows/CAMPAIGN.md) | 2026-10-27 |
| Mesh and external-asset suites added | `harness/unit_mesh.py`, `harness/unit_external.py` | after the 13-suite campaign |
| Public testnet campaign blocked by operator resource admission | [The public testnet](../guides/testnet.md) | 2026-10-28 |
| Public testnet rebuilt with a new genesis and binary | [The public testnet](../guides/testnet.md) | 2026-10-29 |
| Full campaign re-run on the rebuilt testnet | **Not done** | — |
| External audit / mainnet | **Not done** | — |

Two cautions about reading the table:

- The 13-suite devnet campaign predates the mesh and external-asset suites. Those suites have
  their own runs and evidence, but they are not part of the recorded 13-suite result.
- The public testnet was rebuilt after the blocked campaign. Old manifests, keys and genesis
  hashes are invalid. Do not resume a stale campaign.

## What is implemented

The v0.5 tree contains:

- **Kernel and platform** — `Root`, `Clock`, `Verifier`, `Codec`, `Bounds`, `AdminGuard`,
  `Governor`, pure maths and `ClaimCode`.
- **Oracle layer** — per-currency `OracleFeed` with three reporters, `OracleRegistry` and
  `OracleHub` cross-rates.
- **Per-currency stablecoin issuer** — `Stablecoin`, `CollateralCustody`, `RiskParameters`,
  `VaultBook`, `LiquidationEngine`, `SurplusBuffer`, `SavingsPool` and
  `PegStabilityModule`, created in one signed deploy.
- **Accounts and transfers** — one account per owner, owner-gated purses, a public deposit
  facet, measured sends, claim/refund exclusivity, memos, opId idempotency and a native-REV
  stipend.
- **Markets** — sponsor-signed 25-field v4 terms, factory-built pools, seed locks, activation
  checks, swaps through the tradability gate, and LP exit while paused or delisted.
- **Currency mesh** — a USD-first full mesh of direct pairs, with a config file as the source
  of truth for the supported set and priority pairs.
- **Clients** — Rust SDK and CLI, WASM facade and a React web client covering accounts, pay,
  claim, history, vault, savings, PSM redemption, markets, liquidity and read-only
  governance.
- **Formal and verification tooling** — flow YAML, Lean models, TLA+ models, traceability
  checkers, static gates and the behavioural harness.

## What "verified" means here

The project uses four kinds of evidence, recorded in `docs/spec/checks.yaml`:

| Kind | What it proves | Examples |
|---|---|---|
| `static` | The text and structure are internally consistent | flows, inventory, Lean audit, traceability, architecture, captures, mesh config |
| `offline` | Pure models, vectors and client tests pass | Python model tests, market-term vectors, Rust and web unit tests |
| `campaign` | Behaviour on a disposable devnet | the `unit_*` suites and the CLI demo |
| `platform` | A native rholo/ERTP assumption holds | ERTP, REV, atomic rollback, parser limits, finality |

A green static gate does not mean the behaviour is correct on chain. It means the
specification, the model and the harness agree. A campaign suite is stronger evidence, but it
runs on a disposable chain with a pinned node and one validator. None of this is an audit.

## What is explicitly excluded

The following are not missing by accident. They are product decisions recorded in
[`docs/SPEC.md` §19](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#19-exclusions):

| Excluded | Reason |
|---|---|
| Batch payouts | Separate deploys are not atomic; promising batch semantics would be false |
| Ramp registry / fiat ramps | No custody or fiat integration; ramps are licensed off-chain partners |
| CPMM / router / multi-hop | Direct pairs only; the full mesh is the alternative to a router |
| Cards and a platform API | Out of product scope |
| MetaMask signing | Spike specified but not run; no decision |
| OTC / RFQ / limit orders | Not implemented |
| Public-testnet completion | Blocked by upstream node capacity and admission behaviour |
| Merge-gossip arms | Upstream devnet limitation |
| 1 GiB pressure testing | Out of scope by decision |
| Recapitalisation token / debt auction / MKR analogue | Separate workstream |
| Sponsored (meta-transaction) claims | The stipend is a reimbursement, not phlo pre-payment |
| Maker rebates | Deferred |
| Encrypted memo | Plaintext bounded memo only |
| Governance writes in the web UI | CLI/ops only; the web is read-only |
| Direct-delivery transfers | Claim-link transfers only |

## Honest risks

- **The oracle is a committee.** Three allowlisted reporters, median, freshness, spread and
  band checks. If two are compromised, prices can be wrong. The committee is a named trust
  assumption.
- **REV volatility can produce bad debt.** The issuer is REV-only; a sharp fall can leave
  vaults underwater. The surplus buffer absorbs losses first, and new minting halts while
  outstanding bad debt exceeds surplus. There is no backstop beyond that.
- **Ramps are off-chain and unbonded.** A ramp that takes a claim secret and does not pay
  fiat is a trust failure outside the protocol. Allowlisting and local licensing are the
  mitigation; there is no bond in this build.
- **Claim secrets are bearer authority.** Anyone with the secret before expiry can claim.
  Loss is unrecoverable until the sender refunds after expiry. The link keeps the secret in
  the URL fragment, but a screenshot or a chat log can leak it.
- **The chain is pre-testnet.** Consensus residuals, node resource admission and testnet
  resets are external risks. The 2026-10-28 campaign was blocked by exactly this class of
  problem.
- **Interest and savings are not a promise.** There is no fixed rate, no lock and no
  guarantee that borrowers will keep paying. Share value can fall if the pool's assets fall.

## What would change the verdict

A mainnet-ready release would need, at minimum: a full campaign on a stable public testnet,
an external audit of the contracts and economics, licensed ramp partners, a compliance model
for each corridor, and a governance and incident-response process that is more than a 2-of-3
key. None of those is claimed here.

> **Where to go deeper.** The exclusions are normative in
> [`docs/SPEC.md` §19](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#19-exclusions).
> The testing evidence and its limits are described in
> [Testing and the acceptance campaign](../trust/testing.md), and the recorded devnet
> campaign is in
> [`docs/spec/flows/CAMPAIGN.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/flows/CAMPAIGN.md).
