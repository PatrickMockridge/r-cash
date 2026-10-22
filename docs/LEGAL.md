# Legal and regulatory notes (not legal advice)

**This is a devnet-only prototype. It handles no real funds and offers no production service.**

## Activities that may be regulated

Depending on the jurisdiction, the following can require a licence, registration or authorisation:

- issuing or administering a currency-pegged token (e-money, stored value, payment instrument);
- money remittance and cross-border payment services;
- currency exchange / FX dealing;
- operating a payment platform for third parties;
- card issuing and acquiring;
- custody of customer funds.

Target markets include Nigeria, Kenya, Ghana and South Africa, each with its own regime and FX
controls. A permissionless protocol does not make an operator or a ramp partner unregulated.

## Compliance boundary

- The protocol is non-custodial software: users hold their keys and their on-chain balances.
- Fiat on/off-ramp and local payout are performed by ramp partners, who are the regulated
  touchpoints and are responsible for KYC/AML, sanctions screening, record-keeping and tax
  reporting in their jurisdiction.
- The MVP has no fiat custody, no KYC, no sanctions screening and no licensing. It must not be
  presented as a live payments service.
- The mock ramp in the harness is a stand-in, not a partner and not a payment service.

## Before any production deployment

1. Local counsel in every corridor jurisdiction.
2. Licensed ramp/payment partners and a compliance model (KYC, AML, sanctions, transaction
   monitoring, complaints, safeguarding).
3. An external smart-contract and economic audit.
4. A public testnet with real participants and a security review of the node.
5. Consumer disclosures: the stablecoin is not a bank deposit, is not guaranteed, and can lose
   value; the peg is a market outcome, not a promise.

## Tax and accounting

Users, businesses and ramps are responsible for their own tax treatment of conversions, payments and
payouts. The protocol does not compute tax.

## No advice

Nothing in this repository is legal, tax or investment advice.
