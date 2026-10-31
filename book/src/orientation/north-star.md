# The north star

R-Cash is a payments protocol with a position on who gets to hold, move and be paid in money. It
does not begin from a product category. It begins from a problem: the settlement layer for much of
the world is owned by a small number of dollar issuers and the intermediaries around them.

Those choices are not neutral. A stablecoin inherits its issuer's reserve, jurisdiction, freeze
policy and monetary stance. The question of whose currency is the unit of account, and who can stop
a payment, is political.

R-Cash's answer is narrow on purpose: local-currency stablecoins, direct markets between them, and
the account and transfer primitives that make them spendable. Business logic — invoicing, payroll,
logistics, trade finance — is built by other repositories on top. This chapter states the problem,
the premise, the layer boundary and the tests used to resolve qualitative product decisions. It is
explanatory, not normative. **The north star is a direction and a test, not a requirement.**

## The problem

### Stablecoins are political

Money is political, and a stablecoin inherits the politics of its issuer: the reserve it holds, the
jurisdiction it answers to, the addresses it can freeze, and the monetary stance it imports. The
largest stablecoins are dollar instruments issued by centralised entities. USDC and USDT solved a
real problem — a liquid dollar on-chain — and their trust model is still a reserve, a custodian and
a jurisdiction.

That is a legitimate product for dollar access. It is not a neutral base for local-currency
payments. **A decentralised asset with a centralised reserve is a contradiction in the trust layer,
however permissionless the token contract is.**

### The lost momentum

Nikolai Mushegian's death in 2022, the FTX collapse later that year and the 2023 SVB-driven USDC
depeg coincided with a loss of momentum in on-chain DeFi and especially retail Web3. The causes are
multiple and disputed. The effect is visible: activity consolidated around trading, leverage and
dollar yield, while consumer and business use cases did not take their place. Mushegian's death was
a loss to the open-finance and Rholang communities.

### Trading-floor logic and business logic

Hyperliquid is a strong recent example that on-chain markets can be fast and usable. It advanced
the DEX category. It is still an exchange: order books, perpetuals, leverage, liquidation, and
liquidity denominated in dollar stablecoins. That is trading-floor logic.

R-Cash is aimed at the business logic above the settlement layer — the account, the invoice, the
payroll run, the supplier payment — but it supplies the rail those applications stand on, not the
applications themselves. The contrast is categorical, not competitive: a trading venue and a
payments rail solve different problems, and a healthy economy needs both.

### The trust premium in intermediated trade

A cross-border payment or a trade settlement passes through correspondent banks, FX dealers,
compliance providers, local agents and sometimes a dollar stablecoin. Each is paid to hold float,
absorb FX risk, vouch for a counterparty or satisfy a regulator. The trust layer, not the movement
of value, absorbs much of the margin.

"Global South" here is shorthand for lower-income and lower-liquidity markets, not a monolith. The
cost is paid by people sending money home, freelancers paid by foreign clients, and small
businesses paying suppliers and staff across borders. The markets named in this book are design
intent, not current coverage.

### Why payments come first

Roads, rail, ports and bridges have often followed where goods and money already moved. The reverse
also holds: financial levers that are controlled, expensive or heavily taxed can stunt the real
economy that depends on them. Payments come first because settlement is the first common language
of business. A company can choose its accountant, its payroll provider and its logistics platform;
it cannot choose away the payment rail underneath them. R-Cash's job is to provide that rail, not
to write every application that uses it.

## The premise

- **Local unit.** One local stablecoin per currency, REV-collateralised and synthetic, not
  fiat-backed and not USDC, USDT or DAI. Its credibility comes from vaults, an oracle, liquidation,
  a surplus buffer, savings and a peg stability module, with named trust assumptions.
- **Direct settlement.** A full mesh of direct pairs: no router and no mandatory USD hop. **USD is
  retained as the unit of account, default display and pricing anchor; it is removed from the
  settlement path, not from the system.** A native R-Cash USD system exists and is collateralised
  like any other currency.
- **Non-custodial access.** The user's key controls the account. A claim link reaches a recipient
  who has no wallet, but it is bearer authority and the claim costs phlo unless the sender includes
  a stipend.
- **Substrate.** rholo and Rholang supply native REV collateral without a bridge, ERTP payments
  consumed exactly once, capabilities instead of approvals, and atomic deploys with rollback. See
  [Why rholo?](why-rholo.md).
- **The base layer, not the whole stack.** R-Cash is deliberately narrow: local stablecoin
  issuance, stablecoin trading pairs, the currency mesh and its DEX, and the account, purse,
  transfer and claim primitives that make those coins spendable. Invoicing, payroll, logistics,
  shipping, quality control, accounting, letters of credit and trade finance belong in **other
  repositories** that consume R-Cash. Because every business flow ends in a payment, R-Cash is a
  **universal dependency** — the layer without which the rest cannot settle — not a monolith. None
  of the external business logic is implemented here.
- **The wager.** **The wager is not that a token can be neutral. It is that a local unit, backed
  on-chain and settled directly, can be more accountable to its users than a dollar token issued
  elsewhere — and that a dependable settlement layer is the shortest path to a broader economy
  built by others.**

| Layer | Owner | Examples | Today |
|---|---|---|---|
| Settlement and market core | **R-Cash** | local issuers, stablecoin pairs, mesh DEX, accounts, transfers, claim links | implemented on devnet |
| Business logic | **other repos** | invoicing, payroll, logistics, letters of credit, accounting | not in R-Cash |

## The north star in one sentence

**Give anyone a direct, non-custodial balance in their own currency, and make that settlement layer
the universal dependency for the business built elsewhere.**

The first clause is the product. The second is the direction. Neither is a claim that the work is
done. The tests below do not override the authority order: contracts, `docs/SPEC.md` and evidence
govern, and a decision that creates or changes a requirement must be encoded there first.

## A decision framework

Apply the tests in order. Tests 1–3 are gates; tests 4–7 are ordered preferences; test 8 is a
default refusal.

| # | Test | Passes when | Fails when |
|---|---|---|---|
| 1 | **Evidence and status honesty** | Every claim traces to code, `docs/SPEC.md` or evidence, with its status stated | It needs an invented parameter, address, result or status upgrade |
| 2 | **Named trust boundaries** | Oracle, governor, ramp, bootstrap and chain trust stay explicit and isolatable | It hides an admin key, upgrade path or off-chain promise behind an on-chain claim |
| 3 | **Layer discipline** | It is stablecoin issuance, a stablecoin pair, the mesh DEX, or an account/transfer/claim/settlement primitive that other repos consume | It is business logic that belongs in another repo, or it pulls application-specific workflows into the core |
| 4 | **Settlement-path and intermediary removal** | The value path is local-to-local, direct and non-custodial; it removes a party paid only to route, custody, hold float or broker trust | It adds a mandatory dollar hop, wrapper, custodian, hub-reintroducing router or new trust premium |
| 5 | **Local-currency credibility** | It strengthens the local issuer, local liquidity or local unit of account | It substitutes a foreign unit or lets a foreign depeg stop a local payment |
| 6 | **Access without a bank or wallet** | A key, a claim link or a permissionless pair is enough; ramp and KYC stay a partner boundary | It requires a wallet, a bank or a protocol-level allowlist before value moves |
| 7 | **Universal-dependency quality** | It makes R-Cash a cleaner, more stable dependency: reusable primitives, stable interfaces, no application-specific assumptions | It duplicates settlement in a parallel ledger, hard-codes one vertical's workflow, or is a one-off |
| 8 | **Speculative-surface refusal** | It is payment, solvency or market infrastructure | It adds leverage, yield farming, gambling, a governance token or trading for its own sake |

Tests 1–3 are vetoes. Among 4–7 the earlier test wins. Test 8 is a default no that needs a direct,
evidenced payment or credibility justification. A partial failure must be written down, not hidden
inside a broader benefit. Record the decision and any deliberate trade-off in the pull request,
naming the test that was failed.

Quick applications: a payroll feature fails test 3 because it belongs in another repo. A USDC-only
corridor fails tests 4 and 5. A yield farm on LP tokens fails test 8. An invoice-number memo passes
test 3 because the memo is a payment primitive; an invoice lifecycle does not.

## What the north star is not

- **Not a business-logic suite or a monolith.** Invoicing, payroll, logistics, accounting and
  letters of credit belong in other repos that depend on R-Cash.
- **Not decentralised governance today.** Governance is a 2-of-3 admin multisig with a timelock,
  and the oracle is a three-reporter committee; there is no token vote or DAO. The direction is
  fewer required intermediaries and more replaceable trust, not a claim that the destination has
  been reached.
- **Not a dollar-free system.** USD remains the unit of account, default display and pricing
  anchor, and a native USD system exists. The claim is narrower: it is removed from the required
  settlement path.
- **Not live.** It is a v0.5, devnet-only prototype: no real value, no fiat custody, no audit and no
  production deployment. The public-testnet campaign was blocked and has not been re-run as a full
  campaign.
- **Not an audit or a security guarantee.**
- **Not a claim that external business logic exists here.**
- **Not a financial-inclusion promise.** That framing promises an outcome the protocol cannot
  deliver; ramps, KYC/AML and licensing are off-chain partner and legal boundaries.
- **Not a competitor attack on Hyperliquid.** It serves a different job.
- **Not a roadmap commitment or a date.** The later layers are architectural direction, not a
  product, partner or delivery promise.

> **Where to go deeper.** The normative scope is in
> [`docs/SPEC.md` §2](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#2-scope-actors-and-units);
> the USD default and mesh are in
> [§12.4](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#124-currency-mesh-usd-default-and-external-assets);
> the exclusions are in
> [§19](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#19-exclusions). The
> operational consequences are in [Design principles](principles.md); the mechanisms are in
> [The currency mesh](../mechanisms/mesh.md), [Payments and claim links](../mechanisms/payments.md)
> and [Governance and the timelock](../mechanisms/governance.md); the trust boundaries are in
> [Security model](../trust/security-model.md).
