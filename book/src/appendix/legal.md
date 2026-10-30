# Licensing and legal boundaries

**This is a devnet-only prototype. It handles no real funds and offers no production service.
Nothing in this book is legal, tax or investment advice.**

## License

R-Cash is licensed under **AGPL-3.0-only**. Code committed through `d5d613b` was Apache-2.0;
those grants are not revoked. Anyone running a modified version over a network must offer its
source under AGPL §13.

Third-party notices are in
[`THIRD_PARTY_NOTICES.md`](https://github.com/PatrickMockridge/r-cash/blob/main/THIRD_PARTY_NOTICES.md),
including:

- the pinned rholo crates (AGPL-3.0-only);
- the RhoGov signer used as a parity reference (Apache-2.0);
- the r-wallet reference (GPL-3.0; no source is copied in this commit).

The source URL and commit of each dependency are recorded in `Cargo.toml` and the notices
file.

## Activities that may be regulated

Depending on the jurisdiction, the following can require a licence, registration or
authorisation:

- issuing or administering a currency-pegged token (e-money, stored value, payment
  instrument);
- money remittance and cross-border payment services;
- currency exchange or FX dealing;
- operating a payment platform for third parties;
- card issuing and acquiring;
- custody of customer funds.

Target markets include Nigeria, Kenya, Ghana and South Africa, each with its own regime and FX
controls. A permissionless protocol does not make an operator or a ramp partner unregulated.

## The compliance boundary

- The protocol is non-custodial software. Users hold their keys and their on-chain balances.
- Fiat on/off-ramp and local payout are performed by ramp partners. They are the regulated
  touchpoints and are responsible for KYC/AML, sanctions screening, record-keeping and tax
  reporting in their jurisdiction.
- This build has no fiat custody, no KYC, no sanctions screening and no licensing. It must not
  be presented as a live payments service.
- The harness's mock ramp is a stand-in, not a partner and not a payment service.
- The oracle committee and the governor are operational roles, not regulated intermediaries.

## Before any production deployment

1. Local counsel in every corridor jurisdiction.
2. Licensed ramp/payment partners and a compliance model: KYC, AML, sanctions, transaction
   monitoring, complaints and safeguarding.
3. An external smart-contract and economic audit.
4. A public testnet with real participants and a security review of the node.
5. Consumer disclosures: the stablecoin is not a bank deposit, is not guaranteed and can lose
   value; the peg is a market outcome, not a promise.

## Tax and accounting

Users, businesses and ramps are responsible for their own tax treatment of conversions,
payments and payouts. The protocol does not compute tax and does not issue tax statements.

## No advice

Nothing in this repository or this book is legal, tax or investment advice. The authors are
not acting as your lawyer, accountant or adviser. If you intend to operate a service, obtain
advice in the relevant jurisdiction.
