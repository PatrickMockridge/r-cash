# Security model

R-Cash is non-custodial, but it is not trustless. This chapter names the assets, the
adversaries, the mitigations and the residual risks. It is a working threat model for the
v0.5 prototype, not an audit.

## Assets

- Native REV held by the issuer as collateral.
- Local stablecoins held by accounts, pools, the savings pool, the PSM and transfer escrow.
- LP tokens and pool reserves.
- Claim secrets, which are bearer authority over escrowed transfer funds.
- Account ownership, derived from the deployer's public key.
- Vault authority, a one-shot capability created inside the account.
- Oracle prices, used for collateral, FX and the PSM.
- The PSM's REV reserve, which backs par redemption.
- The buffer's surplus, which is first-loss capital.

## Adversaries

| Adversary | Capability |
|---|---|
| A user with a key but no privileges | Can call public arms, create accounts, send transfers |
| A malicious caller of a public arm | Can try to exploit a missing guard or a measured-payment hole |
| A compromised oracle reporter | Can submit a wrong price; needs a quorum to move the median |
| A compromised admin key | One of three; needs two to act |
| A malicious ramp partner | Can take a claim secret and not pay fiat |
| A contract bug | Can consume a cell twice, lose a payment, or commit a partial state |
| A proposer influencing block time | Can shift timestamps; the protocol uses heights for economics |
| A chain-level adversary | Consensus or node faults; out of app scope but a reason this is devnet-only |
| A hostlist advertiser | Can advertise a peer that is not deploy-capable; the client re-verifies |
| A browser compromise | Can read the DOM; the key is in WASM, but a compromised page can still ask it to sign |

## Key threats and mitigations

| Threat | Mitigation |
|---|---|
| A contract steals the deployer id | Only `Account` receives it, only to compare the public key; never stored or emitted; checked by `check_captures` |
| A silent unmatched receive commits a consumed cell | Every arm replies; hot-path awaits are native channels or contracts specified to reply once |
| Partial value movement on failure | Validate before write; deploy-level rollback; a late failure uses `1/0`, not `false` |
| Wrong-brand or wrong-amount payment | Every value arm measures through the issuer; `TransferBook.send` refuses `"amount mismatch"` |
| Double claim or double deposit | ERTP payment consumed once; transfer status checked; claim/refund race on one cell |
| Refund before expiry / claim after expiry | Height checks in `TransferContract`; expiry is checked before the secret |
| Claim secret loss | Sender refunds after expiry; no recovery service; documented |
| Claim link forwarding | Recipient facet is bound at send; a forwarded link cannot redirect funds |
| Oracle manipulation or stale feed | Three reporters, quorum, median, freshness, spread and band; risky arms refuse |
| Reporter key compromise | Quorum threshold; governance can replace reporters; the committee is a named trust |
| Liquidation cascade / bad debt | MCR, close factor, bonus; buffer absorbs; `sin` halts minting; no backstop |
| First-depositor LP inflation | `1e8` shares are never minted; oracle-checked first deposit; floor/ceil rules |
| Rounding drains value | Outputs floor, debts and fees ceil; property tests and Lean arithmetic |
| Ramp takes the secret and does not pay | Allowlisted ramps; no bond in this build; documented trust |
| Forged admin or oracle action | DER signature verification over a canonical preimage; domain nonce; replay guard |
| Channel substitution in an admin action | Actions are signed; Root is frozen after install |
| Registry redirection during install | Root is writable only during bootstrap; freeze is terminal |
| Savings share inflation | Share math uses total assets; no public donation arm; `notify` is capability-only |
| PSM reserve drain | Finite REV reserve; empty reserve refuses; fees stay in the reserve |
| Hostlist poisoning | Entries are advisory; each peer is re-verified against `/status`; writes go to one node |
| Private key in the DOM | Key stays in WASM; encrypted keystore in IndexedDB; password never stored |
| Claim secret leak via storage | Secret stays in the URL fragment; not written to localStorage, IndexedDB or logs |
| Blind retry double-spends | Native op cache and on-chain opId; a cached retry reuses the signed bytes |

## Trust boundaries

| Layer | Trusted party | What it can do |
|---|---|---|
| Accounts, issuance, liquidity, FX, payments, claims | No one beyond the contract rules | Move value only through capability-gated arms |
| Oracle | 2-of-3 reporter committee | Set the median price; a wrong price can trigger liquidations |
| Governance | 2-of-3 admin keys | Change parameters (timelocked), pause, change market status |
| Bootstrap | Installer | Register the initial Root entries; the freeze ends the window |
| Ramps | Licensed partners | Pay out fiat off-chain; can fail or cheat |
| Platform | rholo node and chain | Consensus, ordering, admission, finality |

A user does not trust a custodian with their balance. They do trust the oracle for prices, the
governor for parameter changes, and the chain for ordering and finality. Those are the
boundaries the product must disclose.

## Residual risks

- **Oracle committee.** Two compromised reporters can move the median. The spread and band
  checks bound the damage but do not eliminate it.
- **REV volatility.** A sharp fall can produce bad debt. The buffer absorbs first; residual
  `sin` blocks new minting. There is no debt auction or backstop.
- **PSM reserve.** Redemption is limited by the REV reserve. An empty reserve refuses rather
  than promising fractional cover.
- **Ramps.** Off-chain and unbonded in this build. A ramp can take a secret and not pay.
- **Claim secrets.** Bearer authority. A leaked link can be claimed by anyone before expiry.
- **Governance.** 2-of-3 is a small set. The timelock protects the sharp edges, but an
  emergency pause is immediate.
- **Hostlist.** Discovery is feature-detected and peers are re-verified, but a malicious
  hostlist can still cause a client to try a bad peer; reads fail over, writes do not
  re-submit elsewhere.
- **Browser.** WASM keeps the key out of the DOM, but a compromised page can ask the wallet to
  sign. The user must trust the page they load.
- **Chain.** rholo is pre-testnet. Consensus, resource admission and resets are external
  risks. The 2026-10-28 testnet campaign was blocked by exactly this class of problem.
- **No audit.** The contracts, economics and clients have not been externally audited.

## What is not a security claim

The formal models prove properties of a mathematical model, not of the deployed Rholang. The
behavioural suites exercise a disposable chain. A green static gate means the specification
and the harness agree. None of that is an audit or a mainnet-readiness statement. The
[verification chapter](verification.md) is explicit about the boundary.

> **Where to go deeper.** The normative invariants are in
> [`docs/spec/20-INVARIANTS.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/20-INVARIANTS.md).
> The governance and pause matrix is in
> [`docs/SPEC.md` §13](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#13-governance-timelock-and-pause).
> The capability rules are in
> [`docs/spec/00-CALCULUS.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/00-CALCULUS.md).
