# The web app

The browser client is a React 18 + Vite + TypeScript app that talks to the node through the
Rust SDK compiled to WebAssembly. There is no second TypeScript implementation of the
protocol: signing, term construction, decoding and amount arithmetic are the same code the
CLI uses.

## Running it

```sh
make devnet          # local rholo devnet
make install         # once, to install the contracts and write the manifest
cd web
npm install
npm run dev          # builds the wasm module, syncs the manifest, serves :5173
```

`npm run dev` runs `scripts/build-wasm.mjs` and `scripts/sync-manifest.mjs` before Vite. The
manifest is `deployments/devnet-v4.json`, copied to `web/public/devnet.json`.

Other commands:

| Command | What it does |
|---|---|
| `npm run build` | Typecheck, build WASM and produce `dist/` |
| `npm run typecheck` | TypeScript only |
| `npm test` | Vitest unit tests |
| `npm run test:wasm` | Build WASM and run the Node smoke test |
| `npm run test:e2e` | Build, preview and run the Playwright journey against a running devnet |

The Playwright journey uses two browser wallets, the faucet, the sender's account, a
claimable transfer and the recipient's claim. It needs a live devnet, which is why it is a
manual workflow rather than a unit test.

## Screens

| Route | What it does |
|---|---|
| `/` | Accounts: native REV, per-asset purses, deposit REV, faucet, public key. The currency list comes from `ListingViews.currencies`; the REV balance gates signed reads |
| `/receive` | Public key, REV address, open a claim link |
| `/pay` | Send a claimable transfer: memo, generated opId journaled before submit, optional non-refundable REV stipend, finalized-height expiry, claim link |
| `/claim/:uri/:secret` | Review and claim: status, expiry countdown, memo and stipend; the secret stays in the fragment |
| `/vault` | Collateral, accrued debt, interest, health and rate; deposit, deposit-and-mint, repay, withdraw |
| `/earn` | Savings share value and position; buffer surplus and `sin`; deposit and withdraw |
| `/redeem` | PSM par venue: signed debt, REV reserve, fee and ceiling; redeem stablecoin for REV or mint with REV |
| `/markets` | Mesh matrix and market creation: status, indicative rate, a typed 25-field terms form signed by the wallet |
| `/convert` | Quote and swap; slippage default 50 bps, minimum non-zero |
| `/liquidity` | Seed lock, add and release; non-zero minimum shares and minimum base/quote |
| `/history` | Local journal plus on-chain reconciliation; refund an expired open transfer |
| `/governance` | Read-only risk parameters and pending actions; writes are CLI/ops only |
| `/batch`, `/ramps` | Disabled, with an accurate reason |
| `/settings` | Node URL, manifest, preferred display currency (USD default), keystore export and lock |

No screen uses mock balances, quotes, partners or transactions. A disabled screen says why it
is disabled rather than pretending to work.

## Wallet and secrets

The browser wallet is non-custodial and deliberately small:

- A key is generated **inside WASM**. The UI receives only the REV address and an encrypted
  Web3 Secret Storage v3 keystore.
- The keystore is stored in IndexedDB. The password is never stored. The key is zeroized when
  the wallet locks or the page closes.
- Export downloads the encrypted keystore; import accepts the same document.
- A claim secret lives only in the URL fragment while the claim screen is open. It is not
  written to localStorage, IndexedDB or logs. After a successful claim, the app navigates away
  and clears the fragment.
- The preferred display currency is stored in localStorage. It is not secret and has no
  on-chain state.

MetaMask is not wired in. In the reference wallet it is a read-only identity, and the signing
spike has not been run. The supported path is a locally held encrypted key.

## Reads and freshness

This is the most important operational detail of the web client. `explore-deploy` has no
block context: inside it, `rho:block:data` reports height 0. Every arm that checks oracle
freshness therefore sees a stale feed and refuses.

Consequences:

- **Freshness-gated reads are signed deploys** and cost phlo: oracle prices, pool quotes and
  book quotes.
- A new account with no REV cannot run one. The Accounts screen reads the native REV balance
  first (free) and enables the signed balance read only once the account can pay for it.
- **Public, free reads** are used for values that do not depend on height: transfer records,
  pool parameters, reporters and native REV balances.
- A locked wallet shows "unlock to quote" rather than a zero price.

The client anchors expiry at the finalized height, not the latest tip. A write reports success
only at a finalized block that does not list the deploy in `rejectedDeploys`.

## State

TanStack Query caches node reads with short stale times. Zustand holds the unlocked client
handle, the address and non-secret configuration. The local activity journal lives in
IndexedDB and is labelled as this device's activity; it is not a chain index. Pending entries
are reconciled on boot.

The journal records the transfer URI, asset, amount, expiry, opId, recipient and status. It
never stores a claim secret or a private key.

## What the web client does not do

- It does not sign with MetaMask.
- It does not perform governance writes; those are CLI/ops only.
- It does not expose batch payouts or ramps; both are exclusions.
- It does not invent a price when a feed is missing. It shows the status.
- It does not keep the private key in the DOM. The key stays in WASM.

> **Where to go deeper.** Web requirements are in
> [`docs/SPEC.md` §16](https://github.com/PatrickMockridge/r-cash/blob/main/docs/SPEC.md#16-web-ui).
> The routes are in `web/src/routes/`; the wallet and journal are in `web/src/lib/`. The CLI
> is the scripting surface: [The CLI](cli.md).
