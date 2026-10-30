# Who it is for

R-Cash is a two-sided network: people who hold and move money, and people who supply the
liquidity and collateral that make the money useful. A design that serves one side at the
expense of the other does not survive.

## The people who use it

| Actor | Job to be done | What they touch |
|---|---|---|
| **Individual** | Hold several local currencies, receive from family or an employer, convert, pay a person or merchant | Account, Pay, Claim, Convert |
| **Freelancer** | Invoice a foreign client, receive local currency, withdraw through a ramp | Account, Claim, Convert, local payout partner |
| **SME / business** | Pay suppliers and contractors, hold operating balances | Account, Pay, History |
| **Recipient without a wallet** | Open a claim link, choose a local payout partner, receive mobile money or cash | Claim link, then a ramp |
| **Liquidity provider** | Deposit both sides of a corridor, earn the FX spread | Markets, Liquidity |
| **Vault owner** | Lock REV, mint local currency, repay with interest, withdraw collateral | Vault |
| **Saver** | Hold the stablecoin in the savings pool and earn the interest borrowers pay | Earn |
| **Arbitrageur** | Redeem below par or mint above par through the PSM, trade the residual on the FX market | Redeem, Convert |
| **Ramp partner** | On-ramp fiat and pay out claims on licensed local rails | Off-chain; receives the claim secret |
| **Keeper** | Liquidate unhealthy vaults and watch expiries | Vault, any public arm |
| **Sponsor** | Sign the currency, feed and market terms that bring a corridor to life | Signed deploys and params |
| **Governor** | 2-of-3 admins who schedule parameter changes, pause a currency or change a market status | Governance |

## Three journeys

### The person receiving money

A recipient does not need to understand keys, gas or ERTP. The sender creates the recipient
account and binds the payout facet at send time. The recipient opens a link, sees the amount,
the asset, the expiry and the optional memo, and claims. If they have no REV to pay the claim
deploy, the sender can include a small native-REV stipend.

The honest caveat: the claim is a signed deploy, so someone must pay phlo. The stipend is a
reimbursement sent by the sender in the same deploy as the transfer; it is not a
meta-transaction. If the stipend is zero, the recipient needs a small REV balance or a
third party must execute the claim — and the funds still go to the recipient's bound facet.

### The liquidity provider

An LP supplies both currencies to a market and receives LP tokens. The pool is not a
constant-product curve. It prices against the oracle, applies a base spread plus an inventory
skew, and keeps the fees in reserves, where they accrete to the LP share value.

The seed path is special: the first liquidity is locked until a configured height, and a
market cannot activate until the seed meets the signed terms. This makes the sponsor's
commitment credible before anyone trades. After activation, ordinary LPs can add and remove
liquidity; the seed LP is subject to its lock.

### The vault owner and the saver

A vault owner locks native REV and mints the local stablecoin against it. The vault must stay
above the minimum collateral ratio. Interest accrues every block. On repayment, the payment
splits into principal and interest: principal is burned, interest goes to the surplus buffer,
and the configured share of the buffer's surplus is pushed to savers. Savers hold shares in a
pool; their share value rises without new shares being minted.

The two roles are connected by the same waterfall. The vault owner's interest is the saver's
yield. The buffer stands between them and bad debt: it absorbs losses first, and while
outstanding bad debt exceeds surplus, new minting stops.

## The trust boundaries

Not every participant is equally trusted. The protocol makes the boundaries visible:

| Layer | Who is trusted | Why |
|---|---|---|
| Accounts, issuance, liquidity, FX, payments, claims | No one beyond the contract rules | Non-custodial, atomic, capability-gated |
| Oracle | A 2-of-3 allowlisted reporter committee | Prices must come from somewhere; the committee is the named trust assumption |
| Governance | 2-of-3 admin keys fixed at deploy | Parameter changes and emergency pauses need a human authority |
| Ramps | Licensed partners, off-chain | Fiat payout is a regulated activity and cannot be enforced by the contract |
| Bootstrap | The installer, for one sequence | The Root is written by the installer and then frozen |
| Chain | rholo, currently pre-testnet | Consensus and node behaviour are upstream |

A user does not have to trust a custodian to hold their balance. They do have to trust the
oracle committee for prices and the governor for parameter changes. The
[security model](../trust/security-model.md) examines what that means and what can go wrong.

> **Where to go deeper.** Actors and units are listed in
> [`docs/SPEC.md` §2](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#2-scope-actors-and-units).
> The product framing is in
> [`docs/SPEC.md` §19](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#19-exclusions)
> for what is deliberately out of scope.
