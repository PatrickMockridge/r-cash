# Design principles

Eight principles shape every contract and client decision. They are not marketing copy:
each one has a consequence you can see in the code, and each one rules something out.

## 1. Non-custodial

The user's key controls the account. The protocol never holds user keys and never needs a
custodian to move on-chain value.

**In the code:** one `Account` per owner public key. Owner arms compare the deployer's REV
address with the stored `ownerId`. The `depositFacet` is public but can only receive. The
private key stays in WASM in the browser; the keystore is encrypted into IndexedDB.

**What it rules out:** an operator who can freeze or move a user's balance, account recovery
by a support desk, and "we hold the keys, trust us" onboarding.

## 2. Local currency, not a USD proxy

Every corridor is between two local stablecoins, not routed through a dollar token. Cross
rates are derived from local/USD oracle feeds, but the settlement asset is local.

**In the code:** each currency has its own issuer, collateral, debt ceiling and pools. The
oracle hub computes `rate = floor(basePrice * 1e8 / quotePrice)`. The FX pool holds the two
local assets directly.

**What it rules out:** a single USD stablecoin standing in for every market, and a design
where a dollar depeg or a US bank holiday stops a KES→GHS payment.

## 3. Direct FX

Liquidity providers earn the spread. There is no correspondent-bank leg and no mandatory USD
hop.

**In the code:** a full mesh of direct pairs. One `FxPool` serves an unordered pair in both
directions; `marketFor` resolves either orientation. The mesh has no hub and no router.

**What it rules out:** a router that forces every trade through a few deep pools, and a
CPMM backup venue that would change the risk profile of the LP.

**The honest trade-off:** a full mesh of 16 currencies has 120 possible pairs, but only 24
priority pairs are created and seeded at launch. A non-priority pair is permissionless to
create and otherwise shows as unavailable. Direct pairs mean more markets, each with its own
liquidity, rather than one deep hub.

## 4. Reachable recipients

A claim link plus a local payout partner lets someone receive value without learning about
keys.

**In the code:** `TransferBook.send` escrows the payment in a per-transfer `TransferContract`
holding a hash of a 32-byte secret. The link carries the transfer URI and the secret in the
URL fragment. The recipient facet is bound at send time, so a forwarded link cannot redirect
the funds.

**What it rules out:** requiring the recipient to install a wallet before they can be paid,
and a "claim" that is really a custodial IOU.

**The honest trade-off:** the claim is a signed deploy, so it costs phlo. The optional
native-REV stipend is a reimbursement, not a meta-transaction; without it, the recipient
needs a small REV balance or a third party to execute the claim.

## 5. Risk isolation

Each currency has its own stablecoin issuer, debt ceiling, collateral and pools. A run on one
currency cannot drain another.

**In the code:** one signed `31_stablecoin` deploy per currency creates an independent
`Stablecoin`, `CollateralCustody`, `RiskParameters`, `VaultBook`, `LiquidationEngine`,
`SurplusBuffer`, `SavingsPool` and `PegStabilityModule`. The PSM's REV reserve and the
buffer's surplus are per currency.

**What it rules out:** a shared collateral pool where a naira liquidation consumes the
shilling's backing.

## 6. Capability security

Authority is a name or a signature, not an account number or an allowance. The account is the
only application contract that receives the deployer's `deployerId`, and only to compare the
public key.

**In the code:** mint, burn, custody, liquidation, settlement, PSM, buffer, savings, directory
and market capabilities are held in closures. They are never returned in a reply, stored in a
map, put in a bundle or included in an attestation. Caller-supplied deposit facets are sinks:
they can receive value, never authority.

**What it rules out:** ERC-20-style approvals, a global admin key that can mint any currency,
and a contract that hands a caller a live capability as a "receipt".

## 7. Atomic settlement

One deploy is one transaction. A failed deploy reverts tuple space and native ERTP/REV state;
there are no partial value moves.

**In the code:** every mutating arm follows peek → validate → effect → commit. A refusal
before value moves returns the payment; a refusal after value moves fails the deploy (`1/0`)
so the movement rolls back. State cells carry a `rev` that is revalidated at commit. A swap,
a repay and a claim are each one deploy.

**What it rules out:** a multi-step flow where step three fails and leaves the user's funds in
escrow, and "eventual consistency" between a burn and a mint.

## 8. Honesty about boundaries

Local fiat payout, KYC/AML, cards and licensing are partner and legal boundaries, not
on-chain claims. The protocol does not pretend otherwise.

**In the code:** batch payouts, fiat ramps, a ramp registry, CPMM/router, OTC/RFQ, cards and a
platform API are explicitly excluded. The web client disables Batch and Ramps with a reason.
The status page separates what passed, what is blocked and what was never attempted.

**What it rules out:** a "decentralised" claim over an off-chain payout, and a green check
where the evidence is a blocked testnet.

> **Where to go deeper.** The principles are stated in the project intent and encoded as
> requirements in [`docs/SPEC.md`](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md).
> The capability rules are in
> [`docs/SPEC.md` §3](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#3-system-model-and-authority);
> the exclusions are in
> [§19](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#19-exclusions).
