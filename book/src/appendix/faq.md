# FAQ

### Is R-Cash live? Can I use it with real money?

No. R-Cash is a v0.5, devnet-only prototype on a pre-testnet chain. There is no fiat custody,
no audit and no mainnet deployment. Do not use it with real funds.

### What is R-Cash in one paragraph?

A permissionless multi-currency account and cross-border payments network. It issues a local
stablecoin per currency, runs a DAI-shaped issuer to keep it credible, provides direct FX
markets between currencies, and lets people pay with a wallet or a claim link. The loop is
hold → receive → convert → pay → get paid.

### Is R-Cash decentralised?

Settlement is non-custodial and permissionless, but governance is not decentralised today. A 2-of-3
admin multisig with a timelock can change risk parameters and pause a currency; the oracle is a
three-reporter committee; there is no token vote or DAO. The direction is fewer required
intermediaries and more replaceable trust, not a claim that the destination has been reached. See
[The north star](../orientation/north-star.md).

### Where do payroll, invoicing and logistics live?

In other repositories that consume R-Cash. R-Cash is the settlement and market core — stablecoins,
stablecoin pairs, the mesh DEX and the payment primitives — not the business-logic suite. Those
applications end in a payment that R-Cash supplies. See [The north star](../orientation/north-star.md).

### Is the currency a USD stablecoin?

No. Each currency has its own native stablecoin (rNGN, rKES, …). USD is the default display
and quote currency, and there is a native R-Cash USD system, but the settlement asset in a
KES→GHS payment is always local. The dollar is a reference price, not a required hop.

### Why a full mesh instead of a hub or a router?

A hub routes every trade through a few deep pools, usually USD, which reintroduces the
correspondent-bank dependency. A mesh of direct pairs removes the mandatory hop. The trade-off
is more markets with less liquidity each, so 24 priority pairs are seeded at launch and the
rest are permissionless. See [The currency mesh](../mechanisms/mesh.md).

### Who holds my keys?

You do. The protocol is non-custodial. In the browser the key is generated and held inside
WASM; the page stores an encrypted keystore in IndexedDB. A claim secret is bearer authority
and is never stored on chain.

### What happens if the oracle is wrong or stale?

Actions that increase risk or price new exposure refuse: mint, withdraw, liquidation, PSM
buy/sell and pool quote/swap/add. Repayment, redemption and exit remain available. A wrong
price can still cause liquidations; the oracle committee is a named trust assumption. See
[Security model](../trust/security-model.md).

### What happens if REV crashes?

Vaults can become unhealthy and be liquidated. If a liquidation cannot recover the debt, the
shortfall is booked as bad debt: the surplus buffer absorbs what it can, and the residual
`sin` halts new minting until interest recapitalises the buffer. There is no debt auction, no
MKR analogue and no backstop. See [Liquidation and bad debt](../mechanisms/liquidation.md).

### Why doesn't the recipient need a wallet?

The sender creates the recipient account and binds the payout facet at send time. The
recipient opens a claim link with a secret and claims. The recipient still needs phlo for the
claim deploy; the sender can include a native-REV stipend, or a third party can execute the
claim and the funds still go to the bound facet. See
[Payments and claim links](../mechanisms/payments.md).

### Is there a token I can buy?

No. There is no governance token, no recapitalisation token and no liquidity-mining token.
LP tokens and stablecoins are ERTP assets, not equity.

### What is "Rholphin"?

The name of the Lean 4 formal-specification package under `spec/lean/`. The working directory
is named after it, but the product is R-Cash. It is not a separate network or token.

### Why does a read sometimes cost phlo?

`explore-deploy` has no block context; inside it the block height is 0. Any read that checks
oracle freshness (a quote, a vault health, a pool price) must run as a signed deploy. Public
reads that do not depend on height are free. See [The CLI](../guides/cli.md).

### Is this audited?

No. The formal models prove properties of a mathematical model, not the deployed Rholang. The
behavioural suites run on a disposable chain. None of that is an audit. See
[How the protocol is verified](../trust/verification.md).

### Why is the public testnet not finished?

The 2026-10-28 campaign was blocked by the operator's resource-admission throttle on hosts
below the node's documented minimum. No contract result was involved. The testnet was rebuilt
on 2026-10-29; a full campaign has not been re-run. See
[The public testnet](../guides/testnet.md).

### Can I add a currency or a market?

Yes. Adding a currency is configuration: a feed, an issuer deploy, a registry listing, a
market and a seed. The protocol accepts any registered currency and any direct pair. See
[Adding a currency and a market](../guides/adding-a-currency.md).

### What is the license?

AGPL-3.0-only. Code committed through `d5d613b` was Apache-2.0; those grants are not revoked.
See [Licensing and legal boundaries](legal.md).
