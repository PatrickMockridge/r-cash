# What is R-Cash?

R-Cash is a payments network for people and businesses that move money between currencies.
It is not a bank, a wallet company or a remittance app with a blockchain bolted on. It is a
set of on-chain contracts that make a multi-currency account and a direct FX market possible,
plus clients that expose them.

The one-sentence version: **hold local-currency balances, receive as if local, convert
directly, and pay anyone — with a wallet or a claim link.**

## The problem

Cross-border payments into and across under-served markets are expensive, slow and
structurally intermediated. A payment from Kenya to Ghana normally routes KES → USD → GHS
through correspondent banks. Each hop adds a fee and a delay, and each hop needs a
counterparty with liquidity in the right place at the right time.

Local-currency liquidity is fragmented. Stablecoins for currencies such as the Nigerian
naira or the Kenyan shilling are scarce because major oracle and liquidity providers set
listing thresholds those markets do not meet. The people who pay for this are individuals
sending money home, freelancers paid by foreign clients, and small businesses paying
suppliers and staff across borders.

## The product

R-Cash replaces the correspondent-bank leg with two local stablecoins and a direct market
between them:

- **Hold** — a non-custodial account with a purse per local stablecoin and per LP token.
- **Receive** — an account address, or a claim link that a recipient can open without
  already having a wallet.
- **Convert** — an oracle-priced FX pool for the pair, settled in one atomic deploy.
- **Pay** — a claimable transfer with a secret, an expiry and an optional memo.
- **Get paid** — claim with the secret, or refund after expiry if the recipient never does.

Liquidity providers deposit both sides of a corridor and earn the spread. Vault owners lock
REV and mint local currency. Savers hold the stablecoin in a savings pool and earn the
interest borrowers pay. Arbitrageurs keep the peg by trading between the FX pool and the peg
stability module.

## A worked example

A freelancer in Nairobi invoices a client in Lagos for 100,000 naira.

1. The client holds rNGN in an R-Cash account. They send a claimable transfer for 100,000
   rNGN and copy the claim link.
2. The freelancer opens the link. They do not need an R-Cash account yet; the sender created
   the recipient account and bound the payout facet at send time.
3. The freelancer claims. The rNGN lands in their account.
4. They convert rNGN to rKES through the NGN/KES market. The pool prices the trade from the
   two oracle feeds and charges a spread; the LP who supplied the rKES side earns that
   spread.
5. They withdraw through a local payout partner, or hold rKES and pay a supplier directly.

No leg is routed through a dollar token. The dollar appears only as a reference price in the
oracle cross-rate. The settlement asset is always local.

## What R-Cash is not

- **Not a general DeFi suite.** There is no lending market for arbitrary assets, no yield
  farm, no governance token and no leveraged trading. The economic machinery exists to make
  a payments currency credible, not to maximise speculative surface.
- **Not custodial.** The user's key controls the account. The protocol never holds user keys
  and never needs a custodian to move on-chain value.
- **Not a fiat ramp.** Local fiat on/off-ramp and payout are partner-dependent and happen
  off-chain. The protocol is honest about that boundary; it does not pretend a smart contract
  can pay mobile money by itself.
- **Not a bridge.** Bridged assets can be listed through an adapter, but the protocol does
  not operate a bridge or assume a bridged dollar is worth one dollar.
- **Not live.** This is a v0.5 prototype on a pre-testnet chain. There is no real value, no
  audit and no mainnet deployment.

## The DAI-shaped core

A local stablecoin is only useful if people believe it can be held and redeemed near par.
R-Cash borrows the shape of DAI's economic loop:

| DAI component | R-Cash equivalent |
|---|---|
| Collateralised vaults (`vat`) | Per-currency `VaultBook` holding native REV |
| Stability fee | Per-block interest on vault debt |
| Liquidation | Permissionless liquidation with a close factor and bonus |
| `vow` (surplus buffer, `sin`) | `SurplusBuffer`: interest in, bad debt absorbed, mint halted while short |
| `pot` (savings rate) | `SavingsPool`: borrowers' interest lifts savers' share value |
| `dss-psm` | `PegStabilityModule`: par issuance and redemption against a REV reserve |
| MKR / debt auction | **Deliberately absent.** Bad debt beyond the buffer is an accounting residual, not a token or an auction |

The result is a stablecoin that has a primary issuance mechanism (vaults), a secondary
market (FX pools), a floor and ceiling (the PSM), and a first-loss absorber (the buffer).
The next chapters explain each piece and how they connect.

## Naming

`R-Cash` is the product and repository name. The stablecoins use working names such as
`rNGN` and `rKES`, deliberately distinct from existing `cNGN` tokens and from any
central-bank digital currency. The Lean formal-specification package is called `Rholphin`;
that name is not a separate product. The protocol is not affiliated with a central bank, a
mobile-money operator or an existing stablecoin issuer.

> **Where to go deeper.** The product intent is in
> [`docs/SPEC.md` §2](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#2-scope-actors-and-units).
> The competitive framing and actor list are in [Who it is for](who-it-is-for.md); the
> principles that constrain the design are in [Design principles](principles.md).
