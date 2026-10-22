# R-Cash — Intent

**Status:** v0.1, devnet-only prototype. **Normative specification:** [`SPEC.md`](SPEC.md).

## 1. The problem

Cross-border payments into and across under-served markets are expensive, slow and structurally
intermediated. A KES→GHS payment normally routes KES→USD→GHS through correspondent banks; local
currency liquidity is fragmented; and stablecoins for currencies such as the naira or shilling are
scarce because major oracle and liquidity providers set listing thresholds those markets do not
meet. The cost is paid by individuals sending money home, freelancers paid by foreign clients, and
small businesses paying suppliers and staff across borders.

## 2. The product

**R-Cash is a permissionless multi-currency account and cross-border payments network.** Anyone can
open a non-custodial account holding local currencies, receive money as if they had a local account,
convert directly between currencies, and pay anyone — with a wallet or a claim link — while
liquidity providers, not correspondent banks, earn the FX spread.

R-Cash is not a general DeFi suite. Local-currency stablecoins exist to hold and move money; the FX
pool exists to price and settle conversions and payments; the oracle prices collateral and FX; the
claim link makes a recipient without a wallet reachable; and the ramp layer is the local payout
interface. If a component does not serve **hold → receive → convert → pay → get paid**, it is not in
this build.

## 3. What "Wise-shaped" means here

Wise is not only remittance. Its surface is a multi-currency account with local receiving details,
direct conversion, person-to-person and business payments, batch payouts, invoices, cards and an API
for platforms. R-Cash targets the payments core on-chain:

| Wise surface | R-Cash v0.1 | Status |
|---|---|---|
| Multi-currency account | `Account`: non-custodial purses per local stablecoin and LP token | implemented |
| Direct conversion | withdraw source, `FxPool.swap`, deposit destination (one atomic deploy) | implemented |
| Send money | `TransferBook.send` with a claim hash | implemented |
| Recipient without a wallet | claim secret; local ramp payout off-chain | claim implemented; ramp is a partner boundary |
| Get paid / invoice | `PaymentRequests` | planned |
| Business batch payouts | `TransferBook.sendBatch` | planned |
| Local receiving details | `RampRegistry` on-ramp partners | planned |
| Liquidity / FX revenue | LP tokens in the corridor pool | implemented |
| Cards / API / interest | card issuer, platform API, yield | not in scope |

## 4. Users and jobs

| Actor | Job |
|---|---|
| **Individual** | Hold NGN and KES, receive from family or an employer, convert, pay a person or merchant |
| **Freelancer** | Invoice a foreign client, receive local currency, withdraw through a ramp |
| **SME / business** | Pay suppliers and contractors, batch payroll, hold operating balances |
| **Recipient without a wallet** | Open a claim link, choose a local payout partner, receive mobile money or cash |
| **Liquidity provider** | Deposit both sides of a corridor, earn the FX spread |
| **Local-currency minter** | Lock REV, mint local currency, spend or supply it |
| **Ramp partner** | On-ramp fiat, pay out claims off-chain on licensed local rails |
| **Keeper** | Liquidate unhealthy CDPs, watch expiries |

## 5. Principles

1. **Non-custodial.** The user's key controls the Account. The protocol never holds user keys and
   never needs a custodian to move on-chain value.
2. **Local currency, not a USD proxy.** Every corridor is between two local stablecoins, not routed
   through a dollar token. Cross rates are derived from local/USD oracle feeds, but the settlement
   asset is local.
3. **Direct FX.** Liquidity providers earn the spread; there is no correspondent-bank leg and no
   mandatory USD hop.
4. **Reachable recipients.** A claim link plus a local payout partner lets someone receive value
   without learning about keys.
5. **Risk isolation.** Each currency has its own CDP, debt ceiling, collateral and pools. A run on
   one currency cannot drain another.
6. **Capability security.** Authority is a name or a signature, not an account number or an
   allowance. The Account is the only application contract that receives the deployer's
   `deployerId`, and only to compare the public key.
7. **Atomic settlement.** One deploy is one transaction. A failed deploy reverts tuple space and
   native ERTP/REV state; there are no partial value moves.
8. **Honesty about boundaries.** Local fiat payout, KYC/AML, cards and licensing are partner and
   legal boundaries, not on-chain claims. The protocol does not pretend otherwise.

## 6. Why RChain / rchain-rust

- **Native REV** is the collateral asset, with a native vault and an ERTP brand, so a CDP can custody
  REV without a bridge or a wrapped token.
- **ERTP** provides multi-asset purses, payments consumed exactly once, issuers and amount math,
  which the stablecoins and LP tokens use directly.
- **Capabilities** (`deployerId`, `vaultAuth`, claim secrets, proofs) give a clean authority model
  with no approvals or allowances.
- **Atomic deploys with native-state rollback** let a transfer, a swap and a claim be composed
  safely.
- **Formal culture**: the node carries machine-checked laws in Lean/Coq; R-Cash's specification is
  written to be checkable in the same spirit (see `SPEC.md` §14).

## 7. v0.1 scope

**Implemented and measured on the local devnet:**

- Non-custodial Accounts (per key) with REV, rNGN, rKES and LP-token purses.
- Signed three-reporter oracle with median, freshness, spread and absolute-band checks.
- rNGN and rKES CurrencyZones: REV-collateralised CDP, borrow/repay, interest, MCR, liquidation.
- rNGN/rKES FxPool: oracle-anchored fixed-price market maker, spread + inventory skew, LP tokens,
  add/remove liquidity, swaps both ways.
- TransferBook: quote, send with a claim hash, claim with the secret, refund after expiry.
- M-of-N secp256k1 governance for oracle, zone and pool parameters.

**Not implemented in v0.1:** CPMM backup venue, Router best-of-two, batch payouts, PaymentRequests,
RampRegistry, direct-delivery transfers, multi-hop routing, OTC limit orders/RFQ, cards, API, yield,
user CLI/SDK, web UI, public-testnet deployment.

## 8. Success criteria

**Functional (v0.1):** a fresh devnet runs `make demo` to completion:
- the Account is funded with REV;
- NGN and KES vaults are opened, collateral is deposited and local currency is borrowed;
- liquidity is added to the rNGN/rKES pool, a swap executes and liquidity is removed;
- a claimable transfer is sent, claimed with its secret, and an expired transfer is refunded.

**Economic:** a sender pays the corridor spread, not a correspondent-bank fee; the LP's share of
that spread is measurable; the stablecoin's collateral ratio is enforced on every borrow and
withdrawal; a price fall produces a liquidatable vault and a solvent liquidation.

**Technical:** every state-changing assertion is verified against finalised state; a failed deploy
leaves no partial state; phlo cost per operation is measured; no test relies on an unmeasured claim.

**Safety:** the stated invariants hold in the test suite; the known trust boundaries (oracle
committee, ramps, bootstrap window, pre-testnet chain) are documented and visible to users.

## 9. Trust boundaries

| Layer | v0.1 |
|---|---|
| Accounts, issuance, liquidity, FX, payments, claims | On-chain, non-custodial, atomic |
| Local fiat on/off-ramp and payout | Partner-dependent; off-chain; the MVP uses a recipient key, not a live ramp |
| Oracle | Allowlisted 3-reporter committee |
| Governance | 2-of-3 admin keys, fixed at deploy |
| Bootstrap | Trusted deployer installs the Directory/zones/pool/book and locks the registries |
| Platform | rchain-rust pre-testnet; local devnet only |

## 10. Roadmap

1. **v0.1 (this repo):** corridor core — accounts, local currency CDP, oracle, FPMM, claim/refund.
2. **v0.2:** CPMM backup venue + Router best-of-two; batch payouts; PaymentRequests; RampRegistry and
   a mock ramp; direct-delivery transfers.
3. **v0.3:** multi-hop routing, OTC limit orders/RFQ for size, GHS/UGX/ZAR corridors, protocol fee
   switch, stability-pool/bad-debt backstop.
4. **Production:** public testnet, external audit, licensed ramp partners, KYC/AML and local counsel
   in each corridor, user wallet/UI and a platform API.

## 11. Naming

`R-Cash` is the project and repository name. `rNGN` and `rKES` are working names for the local
stablecoins; they are deliberately distinct from existing `cNGN` tokens and from any central-bank
digital currency. The protocol is not affiliated with a central bank, a mobile-money operator or an
existing stablecoin issuer.

## 12. Status and legal

Devnet-only prototype. The node is pre-testnet (rchain-rust issue #242); no real funds, no fiat
custody, no production use. Stablecoin issuance, FX and payment services are regulated activities in
the target markets; production requires local counsel, licensed ramp partners and a compliance model.
See `STATUS.md`, `THREAT_MODEL.md` and `LEGAL.md`.
