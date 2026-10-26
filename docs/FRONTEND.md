# Frontend

**Status:** R3 is implemented and the browser journey passes against the local devnet.

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
| `/` | Accounts: native REV, per-asset account purses, deposit REV, faucet, public key | Owner balance reads are signed; the REV balance gates them |
| `/receive` | Public key, REV address, open a claim link | A sender needs the public key for a claimable transfer |
| `/convert` | Discover the direct market, quote, then swap with a minimum received | One atomic withdraw→swap→deposit deploy; blocked while the market is not active |
| `/pay` | Send a claimable transfer to a public key | Generates the 32-byte secret and its BLAKE2b hash in wasm; shows the link |
| `/claim/:uri/:secret` | Review and claim a transfer by URI | Secret stays in the URL fragment |
| `/liquidity` | Market slot, reserves, seed lock, add-and-lock, release | Add withdraws both sides and funds the lock; release returns both sides to the account |
| `/batch` | Disabled | Batch payouts are not in the v0.4 protocol |
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