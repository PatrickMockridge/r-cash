# Deployments

Manifests contain public component URIs only. Devnet keys live in `.devnet/` and are
gitignored; no manifest contains a key or a capability.

| File | What it is |
|---|---|
| `devnet-v4.json` | The component manifest written by `make install` (the chain-aware, signed-read installer). Every field is non-null after a completed install. |
| `testnet-v4.json` | The rhobot public-testnet manifest. It is **incomplete**: the 1 GB hosts died before the feeds and stablecoin were listed. Treat missing fields as missing, not as defaults. |
| `devnet.json` | The legacy v0.1 manifest. Historical only. |

Systems (per-currency stablecoins) and markets are **not** in the component manifest.
Clients discover them through `ListingViews.currencies` and `ListingViews.markets`, which
read the `CurrencyRegistry` and `MarketIndex`. This is why adding a currency or a market
does not rewrite the component manifest.

```sh
make install     # install/reinstall the components on a fresh devnet
make bootstrap   # deploy a demo system and the REV/V4T market through the acceptance suites
make setup       # devnet + keys + install + bootstrap in one command
```
