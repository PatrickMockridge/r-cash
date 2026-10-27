//! WASM facade for the browser: wallet, encrypted keystore and the SDK operations.
//!
//! The private key lives only in this module. The UI receives the keystore JSON (for
//! IndexedDB), addresses, and operation results — never a secret except the claim secret,
//! which is bearer authority the sender must see to share.

mod keystore;

use rcash_chain::address::eth_address_from_public_key;
use rcash_chain::deploy::DeployOptions;
use rcash_chain::{ChainError, KeyPair};
use rcash_core::manifest::Manifest;
use rcash_core::Amount;
use rcash_sdk::Client;
use wasm_bindgen::prelude::*;

/// The crate version.
#[wasm_bindgen]
pub fn version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

/// The pinned node revision the client was built against.
/// The BLAKE2b-256 claim hash of a 32-byte secret (hex in, hex out).
#[wasm_bindgen]
pub fn claim_hash(secret_hex: &str) -> Result<String, JsValue> {
    rcash_chain::claim::claim_hash(secret_hex).map_err(js_err)
}

#[wasm_bindgen]
pub fn node_commit() -> String {
    "e2d073dcd02f1e560ccb84749937138a1e184b0b".to_string()
}

/// Sign the R0a parity fixture (test-only).
#[wasm_bindgen]
pub fn parity_sign(secret_hex: &str, term: &str) -> Result<String, JsValue> {
    let key = KeyPair::from_secret_hex(secret_hex).map_err(js_err)?;
    let data = DeployOptions::new(term)
        .timestamp(1_700_000_000_000)
        .phlo(1_000_000, 1)
        .valid_after_block_number(12_345)
        .shard_id("/root")
        .build()
        .map_err(js_err)?;
    let signed = key.sign_deploy(data).map_err(js_err)?;
    let address = key.rev_address().map_err(js_err)?;
    Ok(format!(
        r#"{{"deployer":"{}","signature":"{}","deployId":"{}","address":"{}"}}"#,
        signed.deployer_hex, signed.signature_hex, signed.deploy_id, address
    ))
}

/// A connected wallet and SDK client.
#[wasm_bindgen]
pub struct Rcash {
    node: String,
    manifest: Option<Manifest>,
    v4_manifest: Option<rcash_core::manifest::V4Manifest>,
    client: Option<Client>,
}

#[wasm_bindgen]
impl Rcash {
    /// Create a client for `node` and a deployment manifest (JSON).
    #[wasm_bindgen(constructor)]
    pub fn new(node: &str, manifest_json: &str) -> Result<Rcash, JsValue> {
        let (manifest, v4_manifest) = if manifest_json.contains("\"root_uri\"") {
            (
                None,
                Some(rcash_core::manifest::V4Manifest::from_json(manifest_json).map_err(js_err)?),
            )
        } else {
            (
                Some(Manifest::from_json(manifest_json).map_err(js_err)?),
                None,
            )
        };
        Ok(Self {
            node: node.to_string(),
            manifest,
            v4_manifest,
            client: None,
        })
    }

    /// Generate a key, unlock it, and return the encrypted keystore JSON.
    pub fn create_wallet(&mut self, password: &str) -> Result<String, JsValue> {
        let key = KeyPair::generate().map_err(js_err)?;
        let eth = eth_address_from_public_key(key.public_bytes()).map_err(js_err)?;
        let document = keystore::encrypt(key.secret_bytes(), &eth, password)
            .map_err(|e| JsValue::from_str(&e))?;
        self.client = Some(self.build_client(key));
        Ok(document)
    }

    /// Decrypt a keystore and unlock the wallet. Returns the REV address.
    pub fn unlock(&mut self, document: &str, password: &str) -> Result<String, JsValue> {
        let secret = keystore::decrypt(document, password).map_err(|e| JsValue::from_str(&e))?;
        let key = KeyPair::from_secret_bytes(&secret).map_err(js_err)?;
        let address = key.rev_address().map_err(js_err)?;
        self.client = Some(self.build_client(key));
        Ok(address)
    }

    /// Drop the key from memory.
    pub fn lock(&mut self) {
        self.client = None;
    }

    pub fn is_unlocked(&self) -> bool {
        self.client.is_some()
    }

    /// The unlocked wallet's public key, for receive.
    pub fn public_key(&self) -> Option<String> {
        self.client
            .as_ref()
            .and_then(|client| client.key().map(|key| key.public_hex()))
    }

    /// The unlocked wallet's REV address.
    pub fn address(&self) -> Option<String> {
        self.client
            .as_ref()
            .and_then(|client| client.address().ok())
    }

    /// Encrypt the current key with a (possibly new) password.
    pub fn export_keystore(&self, password: &str) -> Result<String, JsValue> {
        let client = self.client().map_err(js_err)?;
        let key = client
            .key()
            .ok_or_else(|| JsValue::from_str("wallet is locked"))?;
        let eth = eth_address_from_public_key(key.public_bytes()).map_err(js_err)?;
        keystore::encrypt(key.secret_bytes(), &eth, password).map_err(|e| JsValue::from_str(&e))
    }

    /// The current finalized tip height.
    pub async fn height(&self) -> Result<String, JsValue> {
        let height = self.reader().height().await.map_err(js_err)?;
        to_json(serde_json::json!({"height": height}))
    }

    /// Node status.
    pub async fn status(&self) -> Result<String, JsValue> {
        let client = self.reader();
        let status = client.node().status().await.map_err(js_err)?;
        to_json(status)
    }

    /// Native REV balance of an address, in base units.
    pub async fn rev_balance(&self, address: &str) -> Result<String, JsValue> {
        let client = self.reader();
        let balance = client.native_rev_balance(address).await.map_err(js_err)?;
        to_json(serde_json::json!({
            "baseUnits": balance,
            "rev": Amount::raw(balance).to_decimal(),
        }))
    }

    /// Request devnet REV.
    pub async fn faucet(&self, address: &str) -> Result<String, JsValue> {
        let client = self.reader();
        let response = client.node().faucet(address).await.map_err(js_err)?;
        to_json(response)
    }

    /// Account balances for comma-separated assets, in one signed deploy.
    pub async fn balances(&self, assets_csv: &str) -> Result<String, JsValue> {
        let assets: Vec<&str> = assets_csv
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .collect();
        let client = self.client().map_err(js_err)?;
        let balances = client.balances(&assets).await.map_err(js_err)?;
        let amounts: serde_json::Map<String, serde_json::Value> = balances
            .amounts
            .iter()
            .map(|(asset, amount)| {
                (
                    asset.clone(),
                    serde_json::json!({
                        "decimal": amount.to_decimal(),
                        "baseUnits": amount.value(),
                    }),
                )
            })
            .collect();
        to_json(serde_json::json!({
            "ownerId": balances.owner_id,
            "amounts": amounts,
        }))
    }

    /// Fund the Account with REV from the native vault.
    pub async fn deposit_rev(&self, amount: &str) -> Result<String, JsValue> {
        let amount = parse_amount(amount)?;
        let client = self.client().map_err(js_err)?;
        let balance = client.deposit_rev(amount).await.map_err(js_err)?;
        to_json(serde_json::json!({
            "balance": balance.to_decimal(),
            "baseUnits": balance.value(),
        }))
    }

    /// A signed oracle read (accurate freshness).
    pub async fn oracle_price(&self, currency: &str) -> Result<String, JsValue> {
        let client = self.client().map_err(js_err)?;
        let feed = client.oracle_price_signed(currency).await.map_err(js_err)?;
        to_json(serde_json::json!({
            "price": feed.price,
            "height": feed.height,
            "fresh": feed.fresh,
            "reason": feed.reason,
        }))
    }

    /// A signed cross-rate read.
    pub async fn oracle_pair(&self, base: &str, quote: &str) -> Result<String, JsValue> {
        let client = self.client().map_err(js_err)?;
        let rate = client
            .oracle_pair_signed(base, quote)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({
            "rate": rate.rate,
            "fresh": rate.fresh,
            "reason": rate.reason,
        }))
    }

    /// A signed pool quote.
    pub async fn pool_quote(&self, asset_in: &str, amount: &str) -> Result<String, JsValue> {
        let amount = parse_amount(amount)?;
        let client = self.client().map_err(js_err)?;
        let quote = client
            .pool_quote_signed(asset_in, amount)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({
            "amountOut": quote.amount_out,
            "fee": quote.fee,
            "rate": quote.rate,
            "maxIn": quote.max_in,
        }))
    }

    /// Signed quote of the KES side matching an NGN deposit.
    pub async fn pool_quote_add(&self, base: &str) -> Result<String, JsValue> {
        let base = parse_amount(base)?;
        let client = self.client().map_err(js_err)?;
        let quote = client.pool_quote_add_signed(base).await.map_err(js_err)?;
        to_json(serde_json::json!({
            "base": quote.base,
            "quote": quote.quote,
        }))
    }

    /// Signed pool reserves.
    pub async fn pool_reserves(&self) -> Result<String, JsValue> {
        let client = self.client().map_err(js_err)?;
        let reserves = client.pool_reserves_signed().await.map_err(js_err)?;
        to_json(serde_json::json!({
            "reserveBase": reserves.base,
            "reserveQuote": reserves.quote,
            "totalShares": reserves.total_shares,
            "rate": reserves.rate,
            "fresh": reserves.fresh,
            "paused": reserves.paused,
        }))
    }

    pub async fn convert(
        &self,
        from: &str,
        to: &str,
        amount: &str,
        min_out: &str,
    ) -> Result<String, JsValue> {
        let amount = parse_amount(amount)?;
        let min_out = parse_amount(min_out)?;
        let client = self.client().map_err(js_err)?;
        let result = client
            .convert(from, to, amount, min_out)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({
            "amountOut": result.amount_out,
            "fee": result.fee,
        }))
    }

    pub async fn add_liquidity(
        &self,
        base: &str,
        quote: &str,
        min_shares: &str,
    ) -> Result<String, JsValue> {
        let base = parse_amount(base)?;
        let quote = parse_amount(quote)?;
        let min_shares = parse_amount(min_shares)?;
        let client = self.client().map_err(js_err)?;
        let shares = client
            .add_liquidity(base, quote, min_shares)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({ "shares": shares }))
    }

    pub async fn remove_liquidity(
        &self,
        shares: &str,
        min_base: &str,
        min_quote: &str,
    ) -> Result<String, JsValue> {
        let shares = parse_amount(shares)?;
        let min_base = parse_amount(min_base)?;
        let min_quote = parse_amount(min_quote)?;
        let client = self.client().map_err(js_err)?;
        let burned = client
            .remove_liquidity(shares, min_base, min_quote)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({ "shares": burned }))
    }

    /// Send a claimable transfer; returns the transfer id, secret and claim fragment.
    pub async fn send_transfer(
        &self,
        source: &str,
        dest: &str,
        amount: &str,
        min_dest: &str,
        expiry_blocks: i64,
    ) -> Result<String, JsValue> {
        let amount = parse_amount(amount)?;
        let min_dest = parse_amount(min_dest)?;
        let client = self.client().map_err(js_err)?;
        let secret = rcash_chain::claim::generate_secret_hex().map_err(js_err)?;
        let hash = rcash_chain::claim::claim_hash(&secret).map_err(js_err)?;
        let tip = client.node().latest_block_number().await.map_err(js_err)?;
        let expiry = tip + expiry_blocks;
        let transfer_id = client
            .send_transfer(source, dest, amount, min_dest, &hash, expiry)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({
            "transferId": transfer_id,
            "claimSecret": secret,
            "claimHash": hash,
            "expiryHeight": expiry,
            "claimFragment": format!("#/claim/{transfer_id}/{secret}"),
        }))
    }

    pub async fn claim_transfer(
        &self,
        id: i64,
        dest: &str,
        secret: &str,
    ) -> Result<String, JsValue> {
        let client = self.client().map_err(js_err)?;
        let amount = client
            .claim_transfer(id, dest, secret)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({
            "claimed": amount.to_decimal(),
            "baseUnits": amount.value(),
        }))
    }

    pub async fn refund_transfer(&self, id: i64, dest: &str) -> Result<String, JsValue> {
        let client = self.client().map_err(js_err)?;
        let amount = client.refund_transfer(id, dest).await.map_err(js_err)?;
        to_json(serde_json::json!({
            "refunded": amount.to_decimal(),
            "baseUnits": amount.value(),
        }))
    }

    pub async fn transfer_info(&self, id: i64) -> Result<String, JsValue> {
        let client = self.reader();
        let info = client.transfer_info(id).await.map_err(js_err)?;
        to_json(serde_json::json!({
            "sender": info.sender,
            "source": info.source,
            "dest": info.dest,
            "amount": info.amount,
            "claimHash": info.claim_hash_hex,
            "expiry": info.expiry,
            "status": info.status,
        }))
    }

    pub async fn transfer_next_id(&self) -> Result<String, JsValue> {
        let client = self.reader();
        let next = client.transfer_next_id().await.map_err(js_err)?;
        to_json(serde_json::json!({ "nextId": next }))
    }
    // ---- v0.4 surface -------------------------------------------------------

    /// A listed currency's stablecoin and vault URIs.
    pub async fn v4_currency(&self, code: &str) -> Result<String, JsValue> {
        let c = self.reader().v4_currency(code).await.map_err(js_err)?;
        to_json(serde_json::json!({
            "code": c.code, "stablecoinUri": c.stablecoin_uri,
            "vaultUri": c.vault_uri, "paramsHash": c.params_hash, "status": c.status,
        }))
    }

    /// The market record for a direct pair.
    pub async fn v4_market(&self, base: &str, quote: &str) -> Result<String, JsValue> {
        let m = self.reader().v4_market(base, quote).await.map_err(js_err)?;
        match m {
            Some(m) => to_json(serde_json::json!({
                "marketId": m.market_id, "base": m.base, "quote": m.quote,
                "version": m.version, "termsHash": m.terms_hash, "status": m.status,
            })),
            None => to_json(serde_json::Value::Null),
        }
    }

    /// A market's pool and seed-lock URIs.
    pub async fn v4_slot(&self, market: &str) -> Result<String, JsValue> {
        let s = self.reader().v4_slot(market).await.map_err(js_err)?;
        to_json(serde_json::json!({"pool": s.pool_uri, "lock": s.lock_uri}))
    }

    /// A pool's reserves.
    pub async fn v4_reserves(&self, pool: &str) -> Result<String, JsValue> {
        let r = self.reader().v4_reserves(pool).await.map_err(js_err)?;
        to_json(serde_json::json!({
            "base": r.base, "quote": r.quote,
            "totalShares": r.total_shares, "seeded": r.seeded,
        }))
    }

    /// A pool quote for a direction and input amount.
    pub async fn v4_quote(
        &self,
        pool: &str,
        direction: &str,
        amount: &str,
    ) -> Result<String, JsValue> {
        // A v4 quote is a signed read: it needs a block context for oracle freshness.
        let q = self
            .client()
            .map_err(js_err)?
            .v4_quote(pool, direction, parse_amount(amount)?)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({
            "amountOut": q.amount_out, "fee": q.fee, "rate": q.rate,
        }))
    }

    /// The seed lock's state.
    pub async fn v4_lock_info(&self, lock: &str) -> Result<String, JsValue> {
        let l = self.reader().v4_lock_info(lock).await.map_err(js_err)?;
        to_json(serde_json::json!({
            "funded": l.funded, "released": l.released, "cancelled": l.cancelled,
            "untilHeight": l.until_height, "shares": l.shares,
        }))
    }

    /// A stablecoin's total supply.
    pub async fn v4_supply(&self, stablecoin: &str) -> Result<String, JsValue> {
        let supply = self.reader().v4_supply(stablecoin).await.map_err(js_err)?;
        to_json(serde_json::json!({"supply": supply}))
    }

    /// A transfer's public record.
    pub async fn v4_transfer_info(&self, transfer: &str) -> Result<String, JsValue> {
        let t = self.reader().v4_transfer(transfer).await.map_err(js_err)?;
        to_json(serde_json::json!({
            "sender": t.sender, "asset": t.asset, "amount": t.amount,
            "expiry": t.expiry, "status": t.status,
        }))
    }

    /// The unlocked account's balance of one asset.
    pub async fn v4_balance(&self, asset: &str) -> Result<String, JsValue> {
        let balance = self
            .client()
            .map_err(js_err)?
            .v4_balance(asset)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({"asset": asset, "baseUnits": balance}))
    }

    /// Fund the account with REV.
    pub async fn v4_fund_rev(&self, amount: &str) -> Result<String, JsValue> {
        let balance = self
            .client()
            .map_err(js_err)?
            .v4_fund_rev(parse_amount(amount)?)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({"asset": "REV", "baseUnits": balance}))
    }

    /// Send a claimable transfer to a recipient public key.
    pub async fn v4_send_transfer(
        &self,
        to_pub: &str,
        asset: &str,
        amount: &str,
        secret_hash: &str,
        expiry: i64,
    ) -> Result<String, JsValue> {
        let sent = self
            .client()
            .map_err(js_err)?
            .v4_send_transfer(to_pub, asset, parse_amount(amount)?, secret_hash, expiry)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({"id": sent.id, "transfer": sent.uri}))
    }

    /// Claim a transfer with its secret.
    pub async fn v4_claim_transfer(&self, transfer: &str, secret: &str) -> Result<String, JsValue> {
        let balance = self
            .client()
            .map_err(js_err)?
            .v4_claim_transfer(transfer, secret)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({"transfer": transfer, "baseUnits": balance}))
    }

    /// Refund an expired transfer.
    pub async fn v4_refund_transfer(&self, transfer: &str) -> Result<String, JsValue> {
        let balance = self
            .client()
            .map_err(js_err)?
            .v4_refund_transfer(transfer)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({"transfer": transfer, "baseUnits": balance}))
    }

    /// Swap through a pool, depositing the output into the account.
    pub async fn v4_swap(
        &self,
        pool: &str,
        direction: &str,
        asset_in: &str,
        asset_out: &str,
        amount: &str,
        min_out: &str,
    ) -> Result<String, JsValue> {
        let out = self
            .client()
            .map_err(js_err)?
            .v4_swap(
                pool,
                direction,
                asset_in,
                asset_out,
                parse_amount(amount)?,
                parse_amount(min_out)?,
            )
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({"pool": pool, "amountOut": out}))
    }

    /// Add both sides of a market and lock the seed LP.
    pub async fn v4_add_liquidity(
        &self,
        pool: &str,
        lock: &str,
        base: &str,
        quote: &str,
        base_amount: &str,
        quote_amount: &str,
        until_height: i64,
    ) -> Result<String, JsValue> {
        let shares = self
            .client()
            .map_err(js_err)?
            .v4_add_liquidity(
                pool,
                lock,
                base,
                quote,
                parse_amount(base_amount)?,
                parse_amount(quote_amount)?,
                until_height,
            )
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({"shares": shares}))
    }

    /// Release the seed LP and remove it into the account.
    pub async fn v4_release_lp(
        &self,
        lock: &str,
        pool: &str,
        base: &str,
        quote: &str,
    ) -> Result<String, JsValue> {
        let shares = self
            .client()
            .map_err(js_err)?
            .v4_release_lp(lock, pool, base, quote)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({"lock": lock, "shares": shares}))
    }

    /// Mint a stablecoin against REV into the account.
    pub async fn v4_vault_mint(
        &self,
        vault: &str,
        currency: &str,
        collateral: &str,
        mint: &str,
    ) -> Result<String, JsValue> {
        let debt = self
            .client()
            .map_err(js_err)?
            .v4_vault_mint(
                vault,
                currency,
                parse_amount(collateral)?,
                parse_amount(mint)?,
            )
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({"vault": vault, "debt": debt}))
    }

    /// Repay vault debt.
    pub async fn v4_vault_repay(
        &self,
        vault: &str,
        currency: &str,
        amount: &str,
    ) -> Result<String, JsValue> {
        let debt = self
            .client()
            .map_err(js_err)?
            .v4_vault_repay(vault, currency, parse_amount(amount)?)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({"vault": vault, "debt": debt}))
    }

    /// Withdraw REV collateral into the account.
    pub async fn v4_vault_withdraw(&self, vault: &str, amount: &str) -> Result<String, JsValue> {
        let withdrawn = self
            .client()
            .map_err(js_err)?
            .v4_vault_withdraw(vault, parse_amount(amount)?)
            .await
            .map_err(js_err)?;
        to_json(serde_json::json!({"vault": vault, "baseUnits": withdrawn}))
    }
}

impl Rcash {
    fn client(&self) -> Result<&Client, ChainError> {
        self.client
            .as_ref()
            .ok_or_else(|| ChainError::BadKey("wallet is locked".into()))
    }

    fn build_client(&self, key: KeyPair) -> Client {
        let mut client = Client::new(self.node.clone(), key).expect("node URL is valid");
        if let Some(manifest) = &self.manifest {
            client = client.with_manifest(manifest.clone());
        }
        if let Some(manifest) = &self.v4_manifest {
            client = client.with_v4_manifest(manifest.clone());
        }
        client
    }

    /// A keyless client, for public reads that do not need `deployerId`.
    fn reader(&self) -> Client {
        let mut client = Client::reader(self.node.clone()).expect("node URL is valid");
        if let Some(manifest) = &self.manifest {
            client = client.with_manifest(manifest.clone());
        }
        if let Some(manifest) = &self.v4_manifest {
            client = client.with_v4_manifest(manifest.clone());
        }
        client
    }
}

fn js_err(error: impl std::fmt::Display) -> JsValue {
    JsValue::from_str(&error.to_string())
}

fn to_json(value: serde_json::Value) -> Result<String, JsValue> {
    serde_json::to_string(&value).map_err(js_err)
}

fn parse_amount(value: &str) -> Result<i64, JsValue> {
    Amount::parse(value)
        .map(|amount| amount.value())
        .map_err(js_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn signs_the_r0a_fixture_identically() {
        let result = parity_sign(&"01".repeat(32), "Nil").expect("sign");
        assert!(
            result.contains("3044022059126613d09aad982947545c814ee8f4bc44ced6441f70cd8d29840c2d90f78c02206b2e2b145457fd54329096b246e005b64bdaa76ffd94563ec00613bea38d6287"),
            "signature: {result}"
        );
        assert!(
            result.contains("1111pjC8LgoBQApxaJeuGBJWhC4rAQDbVbkSMLaXjGdfiUynCXef9"),
            "address: {result}"
        );
    }
}
