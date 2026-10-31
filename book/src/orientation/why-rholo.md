# Why rholo?

R-Cash is built on [rholo](https://github.com/rhovision-org/rholo), the successor to the
RChain node. The choice is not cosmetic. Four properties of the platform map directly onto
the product's needs, and one of them — native REV — is what makes a collateralised local
stablecoin possible without a bridge.

## Native REV as collateral

The stablecoin issuer needs a collateral asset that it can hold, value and seize. On a chain
where the native token is a first-class ERTP asset, the issuer can custody REV in a purse,
read its balance, and transfer it to a liquidator without a wrapped token or a bridge.

That removes an entire class of risk. There is no wrapped-REV contract to trust, no bridge
validator set, and no redemption queue between the collateral and the issuer. The collateral
is the chain's own asset. Bridged BTC/ETH collateral is a separate future workstream, not a
dependency of the core design.

## ERTP: purses, payments and exact-once consumption

ERTP (the EverydaR Token Protocol) gives every asset an issuer, a purse and a payment. A
payment is a linear value: it can be consumed once, and its amount is measured through the
issuer rather than trusted from the caller. That is exactly the shape a payments protocol
needs.

R-Cash uses ERTP directly:

- A `PurseStore` creates one purse per asset for an account.
- A transfer escrows a payment in a per-transfer contract; claiming deposits it; refunding
  returns it.
- A vault mints a stablecoin payment; a liquidation burns it and seizes REV.
- A pool holds base and quote purses and mints LP tokens.

The "measure, don't trust" rule is why `TransferBook.send` refuses a declared amount that does
not match the payment (`"amount mismatch"`) and why every value arm returns the payment on a
pre-move refusal.

## Capabilities instead of approvals

Authority in Rholang is a name. A contract can hold a mint capability in its closure and never
expose it. A caller can be given a deposit facet that only receives. There is no global
`approve`/`transferFrom` surface to phish and no allowance to revoke.

This is the basis of R-Cash's authority model:

- The account owner is identified by the deployer's REV address, compared inside the account.
- The vault auth is a one-shot capability created inside the account and never returned.
- The issuer's mint, burn, custody, settlement and PSM capabilities live only in closures.
- An attestation identifies a template and a currency; it never returns a capability or a key.

Capability discipline is checked statically: `tools/check_captures.py` rejects a capability
that appears in a reply, a stored map, a bundle or an attestation.

## Atomic deploys with rollback

A deploy is one transaction. If any arm fails, tuple space and native REV/ERTP state roll
back. That lets R-Cash compose a conversion, a repayment or a claim as one atomic step
without an escrow contract in the middle.

The pattern is visible in the repay waterfall: settle the payment (burn principal, deposit
interest), call `cover(0)` to reconcile bad debt, then `paySavings` — all in one deploy. If a
later step fails, the earlier burn is rolled back. There is no window where principal is
burned but interest is lost.

It also imposes discipline. An arm that has already moved value cannot "return false"; it must
fail the deploy so the movement rolls back. A refusal that still holds a payment must return
it in the refusal tuple. These rules are invariants, not style preferences.

## A formal culture

The rholo ecosystem treats specifications as first-class. R-Cash follows that norm:

- The contract core has a component calculus with laws, non-laws and composition protocols.
- Every state-changing arm is described in a flow YAML with its guards, effects, access and
  refusals.
- Invariants are modelled in Lean 4, with no `sorry`, `admit` or `native_decide`, and an
  axiom audit.
- Five concurrency models are written in TLA+.
- A traceability checker requires every requirement to map to acceptance criteria, evidence
  and a model transition.

This does not mean the contracts are formally verified end to end. The Lean model is a
mathematical model, not an extraction from the Rholang. The link to the deployed code is
traceability plus tests. The [verification chapter](../trust/verification.md) is explicit
about the boundary.

## What the platform constrains

Building on rholo also means accepting its limits. The contracts are shaped by measured
platform behaviour:

- A deploy term is at most 65,536 bytes; the parser depth is 128.
- A failed deploy rolls back tuple space and native state.
- An unmatched `for` is silent, so every arm must reply or be deliberately fire-and-forget.
- BigInt intermediates need `.toInt()` at fixed-point boundaries.
- Rholang has no built-in decimal type: the exact decimal added in October 2026 was removed
  before mainnet (issue #527). R-Cash never used it; every amount is an 8-decimal integer count
  of base units, and decimal strings are only an input format at the client edge.
- `explore-deploy` has no block context, so freshness-gated reads must be signed deploys.

These are not incidental trivia. They explain why the stablecoin system is one deploy, why
the bootstrap is split into steps, and why the client signs reads that depend on block
height. The [repository map](../trust/repository-map.md) lists the languages and where each
kind of code lives.

> **Where to go deeper.** The deploy and authority rules are in
> [`docs/SPEC.md` §3](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#3-system-model-and-authority).
> The component calculus is in
> [`docs/spec/00-CALCULUS.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/spec/00-CALCULUS.md).
> Platform limits and measured costs are summarised in
> [Repository and implementation map](../trust/repository-map.md).
