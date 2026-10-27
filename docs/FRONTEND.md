# Frontend

**Status:** the v0.5 screens are implemented and the static gates are green. The browser
journey is rerun in the final behavioural campaign, not before it.

React 18 + Vite 6 + TypeScript. The product code talks to the node through the Rust SDK
compiled to WebAssembly (`crates/rcash-wasm`), so signing, term construction, decoding and
protocol semantics are the same code the CLI uses — there is no second TypeScript
implementation of the protocol.

## Run

```sh
make devnet                      # local rholo devnet
make install                     # once, to install the contracts and write the manifest
cd web
npm install
npm run dev                      # builds the wasm module, copies the manifest, serves :5173
```

`npm run build` produces `dist/`. `npm run test` runs the unit tests. `npm run test:e2e`
builds the app, serves `dist` with `vite preview`, and runs the v0.4 journey against a
running devnet: two browser wallets, the faucet, funding the sender's account, a
claimable transfer, the recipient's claim, and the credited purse. The manifest is
`public/devnet.json`, synced from `deployments/devnet-v4.json`.

## Screens

| Route | What it does | Notes |
|---|---|---|
| `/` | Accounts: native REV, per-asset account purses, deposit REV, faucet, public key | Currency list comes from `ListingViews.currencies`; the REV balance gates the signed reads |
| `/receive` | Public key, REV address, open a claim link | A sender needs the public key for a claimable transfer |
| `/pay` | Send a claimable transfer | Memo, generated opId journaled before submit, optional non-refundable REV stipend, finalized-height expiry, claim link |
| `/claim/:uri/:secret` | Review and claim a transfer | Status, expiry countdown, memo and stipend; the secret stays in the fragment |
| `/vault` | Vault position and lifecycle | Collateral, accrued debt, interest, health and rate; deposit, deposit-and-mint, repay, withdraw |
| `/earn` | Savings pool and surplus buffer | Share value, position, buffer surplus/sin, savers' share; deposit and withdraw |
| `/redeem` | PSM par venue | Signed debt, REV buffer, fee and ceiling; redeem stablecoin for REV or mint with REV |
| `/markets` | Market list and creation | Lists status and links to seeding/conversion; creates a market from a typed 25-field JSON terms object signed by the wallet |
| `/convert` | Quote and swap | Slippage default 50 bps; the minimum received is derived from the quote and must be non-zero |
| `/liquidity` | Seed lock, add and release | Non-zero minimum shares and minimum base/quote; release is the LP exit while paused |
| `/history` | Local journal and on-chain reconciliation | Refunds an open transfer after its expiry height |
| `/governance` | Read-only risk parameters and pending actions | Writes are CLI/ops only |
| `/batch` | Disabled | Batch payouts are an explicit exclusion |
| `/ramps` | Disabled | Off-chain licensed-partner boundary |
| `/settings` | Node URL, manifest, export keystore, lock | Only non-secret config is stored |

The manifest is `deployments/devnet-v4.json`, copied to `public/devnet.json` by
`scripts/sync-manifest.mjs`; the wasm constructor recognises a v0.4 document by its
`root_uri` field.

No screen uses mock balances, quotes, partners or transactions. Disabled screens say why.

## Wallet and secrets

- A key is generated inside the wasm module; the UI receives only the REV address and the
  encrypted Web3 Secret Storage v3 keystore.
- The keystore is stored in IndexedDB; the password is never stored. The key is zeroized
  when the wallet locks or the page closes.
- Export downloads the encrypted keystore. Import accepts the same document.
- A claim secret lives only in the URL fragment while the claim screen is open. It is not
  written to localStorage, IndexedDB or logs. After a successful claim the app navigates
  away, clearing the fragment.
- MetaMask is not wired in: in r-wallet it is a read-only identity, and the R0b spike has
  not been run (`SPIKE-METAMASK.md`).

## Reads and freshness

`explore-deploy` has no block context: `rho:block:data` reports height 0 there. Every
freshness-gated read (oracle, pool quote, book quote) is therefore a
**signed deploy**, which costs phlo. A new account with no REV cannot run one; the Accounts
screen reads the native REV balance first (free) and only enables the signed balance read
once the account can pay for it.

Values that do not depend on freshness stay public and free: transfer records, pool and
zone parameters, reporters, native REV balances.

## State

TanStack Query caches node reads with short stale times; zustand holds the unlocked client
handle, address and non-secret configuration. The local activity journal lives in
IndexedDB and is labelled as this device's activity — it is not a chain index.