//! v0.4 client surface: accounts, transfers, stablecoins and markets.
//!
//! Reads that do not depend on freshness use `explore-deploy`; owner arms and any
//! arm that checks an oracle or a height run as signed deploys. Every term is
//! rendered from typed values; no caller text reaches Rholang.

use std::collections::BTreeMap;

use rcash_chain::rho_expr::{Reply, RhoValue};
use rcash_chain::ChainError;
use rcash_core::manifest::V4Manifest;

use crate::{terms, Client};

/// A listed currency's live system.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4Currency {
    pub code: String,
    pub stablecoin_uri: String,
    pub vault_uri: String,
    pub params_hash: String,
    pub status: String,
}

/// A market record from the index.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4Market {
    pub market_id: String,
    pub base: String,
    pub quote: String,
    pub version: i64,
    pub terms_hash: String,
    pub status: String,
}

/// Pool reserves.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4Reserves {
    pub base: i64,
    pub quote: i64,
    pub total_shares: i64,
    pub seeded: bool,
}

/// A transfer's public record.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4Transfer {
    pub sender: String,
    pub asset: String,
    pub amount: i64,
    pub expiry: i64,
    pub status: String,
}

/// A market's pool and seed-lock URIs.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4Slot {
    pub pool_uri: String,
    pub lock_uri: String,
}

/// A created transfer's handle.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4Sent {
    pub id: i64,
    pub uri: String,
}

fn decode(message: impl Into<String>) -> ChainError {
    ChainError::Decode(message.into())
}

fn int_at(values: &[RhoValue], index: usize) -> Result<i64, ChainError> {
    values
        .get(index)
        .and_then(RhoValue::as_int)
        .ok_or_else(|| decode("expected an integer"))
}

fn str_at(values: &[RhoValue], index: usize) -> Result<String, ChainError> {
    values
        .get(index)
        .and_then(RhoValue::as_str)
        .map(str::to_string)
        .ok_or_else(|| decode("expected a string"))
}

fn map_at(values: &[RhoValue], index: usize) -> Result<&BTreeMap<String, RhoValue>, ChainError> {
    values
        .get(index)
        .and_then(RhoValue::as_map)
        .ok_or_else(|| decode("expected a map"))
}

fn field<'a>(map: &'a BTreeMap<String, RhoValue>, key: &str) -> Result<&'a RhoValue, ChainError> {
    map.get(key)
        .ok_or_else(|| decode(format!("missing field {key}")))
}

fn field_str(map: &BTreeMap<String, RhoValue>, key: &str) -> Result<String, ChainError> {
    field(map, key)?
        .as_str()
        .map(str::to_string)
        .ok_or_else(|| decode(format!("field {key} is not a string")))
}

fn field_int(map: &BTreeMap<String, RhoValue>, key: &str) -> Result<i64, ChainError> {
    field(map, key)?
        .as_int()
        .ok_or_else(|| decode(format!("field {key} is not an integer")))
}

impl Client {
    fn require_v4(&self) -> Result<&V4Manifest, ChainError> {
        self.v4_manifest().ok_or_else(|| {
            ChainError::Core(rcash_core::CoreError::BadManifest(
                "client has no v0.4 manifest; load deployments/devnet-v4.json".into(),
            ))
        })
    }

    async fn v4_read(&self, uri: &str, args: &str) -> Result<Reply, ChainError> {
        let term = format!(
            "new return, rl(`rho:registry:lookup`), capCh, resCh in {{ \
             rl!(`{uri}`, *capCh) | for (cap <- capCh) {{ \
             cap!({args}, *resCh) | for (@r <- resCh) {{ return!(r) }} }} }}"
        );
        self.explore_reply(&term).await
    }

    fn v4_account_term(&self, body: &str) -> Result<String, ChainError> {
        let factory = self.require_v4()?.account_factory_uri.as_str().to_string();
        Ok(format!(
            "new deployerId(`rho:rchain:deployerId`), \
             deployerIdOps(`rho:rchain:deployerId:ops`), \
             rl(`rho:registry:lookup`), factoryCh, accountCh, pkCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{factory}`, *factoryCh) | \
             deployerIdOps!(\"pubKeyBytes\", *deployerId, *pkCh) | \
             for (AccountFactory <- factoryCh; @pk <- pkCh) {{ \
             AccountFactory!(\"getOrCreate\", pk, *accountCh) | \
             for (@(true, account, ownerId) <- accountCh) {{ {body} }} }} }}"
        ))
    }

    async fn v4_tx(&self, body: &str) -> Result<Reply, ChainError> {
        let term = self.v4_account_term(body)?;
        let value = self.signed_value(&term).await?;
        Reply::from_value(&value)
    }

    /// The v0.4 manifest attached to this client.
    pub fn v4_manifest(&self) -> Option<&V4Manifest> {
        self.v4_manifest.as_ref()
    }

    /// Attach the v0.4 deployment manifest.
    pub fn with_v4_manifest(mut self, manifest: V4Manifest) -> Self {
        self.v4_manifest = Some(manifest);
        self
    }

    // ---- public reads -------------------------------------------------------

    /// A listed currency's live stablecoin and vault URIs.
    pub async fn v4_currency(&self, code: &str) -> Result<V4Currency, ChainError> {
        let views = self.require_v4()?.listing_views_uri.as_str().to_string();
        let reply = self
            .v4_read(&views, &format!("\"currency\", {}", terms::s(code)?))
            .await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        Ok(V4Currency {
            code: code.to_string(),
            stablecoin_uri: field_str(entry, "stablecoinUri")?,
            vault_uri: field_str(entry, "vaultUri")?,
            params_hash: field_str(entry, "paramsHash")?,
            status: field_str(entry, "status")?,
        })
    }

    /// The market for a direct pair, if one is staged or active.
    pub async fn v4_market(&self, base: &str, quote: &str) -> Result<Option<V4Market>, ChainError> {
        let views = self.require_v4()?.listing_views_uri.as_str().to_string();
        let reply = self
            .v4_read(
                &views,
                &format!("\"marketFor\", {}, {}", terms::s(base)?, terms::s(quote)?),
            )
            .await?;
        match reply {
            Reply::Refused(_) => Ok(None),
            Reply::Ok(values) => {
                let entry = map_at(&values, 0)?;
                Ok(Some(V4Market {
                    market_id: field_str(entry, "marketId")?,
                    base: field_str(entry, "base")?,
                    quote: field_str(entry, "quote")?,
                    version: field_int(entry, "version")?,
                    terms_hash: field_str(entry, "termsHash")?,
                    status: field_str(entry, "status")?,
                }))
            }
        }
    }

    /// Whether a market is active.
    pub async fn v4_is_active(&self, market_id: &str) -> Result<bool, ChainError> {
        let views = self.require_v4()?.listing_views_uri.as_str().to_string();
        let reply = self
            .v4_read(&views, &format!("\"isActive\", {}", terms::s(market_id)?))
            .await?;
        let values = reply.into_result()?;
        values
            .first()
            .and_then(RhoValue::as_bool)
            .ok_or_else(|| decode("isActive did not return a boolean"))
    }

    /// A market's pool and seed-lock URIs from the directory.
    pub async fn v4_slot(&self, market_id: &str) -> Result<V4Slot, ChainError> {
        let directory = self.require_v4()?.market_directory_uri.as_str().to_string();
        let reply = self
            .v4_read(&directory, &format!("\"byId\", {}", terms::s(market_id)?))
            .await?;
        let values = reply.into_result()?;
        let slot = map_at(&values, 0)?;
        Ok(V4Slot {
            pool_uri: field_str(slot, "poolUri")?,
            lock_uri: field_str(slot, "lockUri")?,
        })
    }

    /// A pool's reserves.
    pub async fn v4_reserves(&self, pool_uri: &str) -> Result<V4Reserves, ChainError> {
        let reply = self.v4_read(pool_uri, "\"reserves\"").await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        Ok(V4Reserves {
            base: field_int(entry, "base")?,
            quote: field_int(entry, "quote")?,
            total_shares: field_int(entry, "totalShares")?,
            seeded: field(entry, "seeded")?
                .as_bool()
                .ok_or_else(|| decode("seeded is not a boolean"))?,
        })
    }

    /// A stablecoin's total supply.
    pub async fn v4_supply(&self, stablecoin_uri: &str) -> Result<i64, ChainError> {
        let reply = self.v4_read(stablecoin_uri, "\"supply\"").await?;
        let values = reply.into_result()?;
        int_at(&values, 0)
    }

    /// A transfer's public record.
    pub async fn v4_transfer(&self, transfer_uri: &str) -> Result<V4Transfer, ChainError> {
        let reply = self.v4_read(transfer_uri, "\"info\"").await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        Ok(V4Transfer {
            sender: field_str(entry, "sender")?,
            asset: field_str(entry, "asset")?,
            amount: field_int(entry, "amount")?,
            expiry: field_int(entry, "expiry")?,
            status: field_str(entry, "status")?,
        })
    }

    // ---- account writes -----------------------------------------------------

    /// One asset balance of the caller's account.
    pub async fn v4_balance(&self, asset: &str) -> Result<i64, ChainError> {
        let body = format!(
            "new r in {{ @account!(\"balance\", *deployerId, {}, *r) | \
             for (@x <- r) {{ deployId!(x) }} }}",
            terms::s(asset)?
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }

    /// Fund the caller's account with REV from the native vault.
    pub async fn v4_fund_rev(&self, amount: i64) -> Result<i64, ChainError> {
        if amount <= 0 {
            return Err(decode("amount must be positive"));
        }
        let body = format!(
            "new fCh, eCh, iCh, pCh, fundCh, wCh, dCh in {{ \
             @account!(\"depositFacet\", \"REV\", *fCh) | \
             for (@f <- fCh) {{ match f {{ (true, facet) => {{ \
             rl!(`rho:rchain:ertp`, *eCh) | \
             for (@(_, ERTP) <- eCh) {{ \
             @ERTP!(\"getRevIssuer\", *iCh) | \
             for (@(revBrand, issuer) <- iCh) {{ \
             @issuer!(\"makeEmptyPurse\", *pCh) | \
             for (@(true, purse) <- pCh) {{ \
             @purse!(\"revFund\", *deployerId, {amount}, *fundCh) | \
             for (@_ <- fundCh) {{ \
             @purse!(\"withdraw\", (revBrand, {amount}), *wCh) | \
             for (@(true, payment) <- wCh) {{ \
             @facet!(\"deposit\", payment, *dCh) | \
             for (@dd <- dCh) {{ deployId!(dd) }} }} }} }} }} }} }} \
             _ => {{ deployId!(f) }} }} }} }}"
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }

    /// Send a claimable transfer to a recipient's public key.
    pub async fn v4_send_transfer(
        &self,
        recipient_pub_hex: &str,
        asset: &str,
        amount: i64,
        secret_hash_hex: &str,
        expiry: i64,
    ) -> Result<V4Sent, ChainError> {
        if amount <= 0 {
            return Err(decode("amount must be positive"));
        }
        let hash = rcash_core::rho::hex_bytes(secret_hash_hex)?;
        let body = format!(
            "new rfCh, roCh, rfacetCh, sCh in {{ \
             rl!(`{factory}`, *rfCh) | \
             for (RecipientFactory <- rfCh) {{ \
             RecipientFactory!(\"getOrCreate\", \"{recipient_pub_hex}\".hexToBytes(), *roCh) | \
             for (@(true, recipient, _) <- roCh) {{ \
             @recipient!(\"depositFacet\", {asset_lit}, *rfacetCh) | \
             for (@rf <- rfacetCh) {{ match rf {{ \
               (true, facet) => {{ \
                 @account!(\"sendTransfer\", *deployerId, {asset_lit}, facet, {amount}, \
                           {hash}, {expiry}, *sCh) | \
                 for (@s <- sCh) {{ match s {{ \
                   (true, id, uri) => deployId!((true, id, uri)) \
                   _ => deployId!(s) }} }} }} \
               _ => deployId!(rf) }} }} }} }} }}",
            factory = self.require_v4()?.account_factory_uri.as_str(),
            recipient_pub_hex = recipient_pub_hex,
            asset_lit = terms::s(asset)?,
            amount = amount,
            hash = hash,
            expiry = expiry,
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        Ok(V4Sent {
            id: int_at(&values, 0)?,
            uri: str_at(&values, 1)?,
        })
    }

    /// Claim a transfer with its secret.
    pub async fn v4_claim_transfer(
        &self,
        transfer_uri: &str,
        secret_hex: &str,
    ) -> Result<i64, ChainError> {
        let secret = rcash_core::rho::hex_bytes(secret_hex)?;
        let body = format!(
            "new r in {{ @account!(\"claimTransfer\", *deployerId, `{transfer_uri}`, {secret}, *r) | \
             for (@x <- r) {{ deployId!(x) }} }}"
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }

    /// Refund an expired transfer into the caller's account.
    pub async fn v4_refund_transfer(&self, transfer_uri: &str) -> Result<i64, ChainError> {
        let body = format!(
            "new r in {{ @account!(\"refundTransfer\", *deployerId, `{transfer_uri}`, *r) | \
             for (@x <- r) {{ deployId!(x) }} }}"
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }

    // ---- markets ------------------------------------------------------------

    /// Swap from the caller's account and deposit the output back into it.
    pub async fn v4_swap(
        &self,
        pool_uri: &str,
        direction: &str,
        asset_in: &str,
        asset_out: &str,
        amount: i64,
        min_out: i64,
    ) -> Result<i64, ChainError> {
        if direction != "b2q" && direction != "q2b" {
            return Err(decode("direction must be b2q or q2b"));
        }
        let body = format!(
            "new wCh, pCh, sCh, dCh in {{ \
             @account!(\"withdraw\", *deployerId, {asset_in_lit}, {amount}, *wCh) | \
             for (@(true, payment) <- wCh) {{ \
             rl!(`{pool_uri}`, *pCh) | for (FxPool <- pCh) {{ \
             FxPool!(\"swap\", \"{direction}\", payment, {min_out}, *sCh) | \
             for (@s <- sCh) {{ match s {{ \
               (true, outPayment, out) => {{ \
                 @account!(\"deposit\", *deployerId, {asset_out_lit}, outPayment, *dCh) | \
                 for (@_ <- dCh) {{ deployId!((true, out)) }} }} \
               _ => {{ deployId!(s) }} }} }} }} }} }}",
            asset_in_lit = terms::s(asset_in)?,
            asset_out_lit = terms::s(asset_out)?,
            amount = amount,
            min_out = min_out,
            direction = direction,
            pool_uri = pool_uri,
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }

    /// Release the seed LP after the lock height and remove it, depositing both
    /// sides back into the caller's account.
    pub async fn v4_release_lp(
        &self,
        lock_uri: &str,
        pool_uri: &str,
        base_asset: &str,
        quote_asset: &str,
    ) -> Result<i64, ChainError> {
        let body = format!(
            "new lCh, rCh, pCh, rrCh, d1, d2 in {{ \
             rl!(`{lock_uri}`, *lCh) | for (LiquidityLock <- lCh) {{ \
             LiquidityLock!(\"release\", *deployerId, *rCh) | \
             for (@r <- rCh) {{ match r {{ \
               (true, lpPayment, shares) => {{ \
                 rl!(`{pool_uri}`, *pCh) | for (FxPool <- pCh) {{ \
                 FxPool!(\"removeLiquidity\", lpPayment, 0, 0, *rrCh) | \
                 for (@rr <- rrCh) {{ match rr {{ \
                   (true, basePayment, quotePayment) => {{ \
                     @account!(\"deposit\", *deployerId, {base_lit}, basePayment, *d1) | \
                     @account!(\"deposit\", *deployerId, {quote_lit}, quotePayment, *d2) | \
                     for (@_ <- d1; @_ <- d2) {{ deployId!((true, shares)) }} }} \
                   _ => {{ deployId!(rr) }} }} }} }} }} \
               _ => {{ deployId!(r) }} }} }} }} }}",
            base_lit = terms::s(base_asset)?,
            quote_lit = terms::s(quote_asset)?,
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }

    // ---- stablecoin issuer --------------------------------------------------

    /// Open or reuse a vault, deposit REV and mint the stablecoin into the account.
    pub async fn v4_vault_mint(
        &self,
        vault_uri: &str,
        currency: &str,
        collateral: i64,
        mint: i64,
    ) -> Result<i64, ChainError> {
        let body = format!(
            "new zCh, wCh, vCh, dCh, mCh, sdCh in {{ \
             @account!(\"vaultOpen\", *deployerId, `{vault_uri}`, *zCh) | \
             for (@z <- zCh) {{ match z {{ (true, auth) => {{ \
             @account!(\"withdraw\", *deployerId, \"REV\", {collateral}, *wCh) | \
             for (@(true, collateralPayment) <- wCh) {{ \
             rl!(`{vault_uri}`, *vCh) | for (VaultBook <- vCh) {{ \
             VaultBook!(\"deposit\", ownerId, auth, collateralPayment, *dCh) | \
             for (@dd <- dCh) {{ match dd {{ (true, _) => {{ \
               VaultBook!(\"mint\", ownerId, auth, {mint}, *mCh) | \
               for (@m <- mCh) {{ match m {{ \
                 (true, stablePayment, debt) => {{ \
                   @account!(\"deposit\", *deployerId, {currency_lit}, stablePayment, *sdCh) | \
                   for (@_ <- sdCh) {{ deployId!((true, debt)) }} }} \
                 _ => {{ deployId!(m) }} }} }} }} _ => {{ deployId!(dd) }} }} }} \
             }} }} }} _ => {{ deployId!(z) }} }} }} }}",
            currency_lit = terms::s(currency)?,
            collateral = collateral,
            mint = mint,
            vault_uri = vault_uri,
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }

    /// Repay vault debt with the account's stablecoin.
    pub async fn v4_vault_repay(
        &self,
        vault_uri: &str,
        currency: &str,
        amount: i64,
    ) -> Result<i64, ChainError> {
        let body = format!(
            "new zCh, wCh, vCh, rCh in {{ \
             @account!(\"vaultOpen\", *deployerId, `{vault_uri}`, *zCh) | \
             for (@z <- zCh) {{ match z {{ (true, auth) => {{ \
             @account!(\"withdraw\", *deployerId, {currency_lit}, {amount}, *wCh) | \
             for (@(true, payment) <- wCh) {{ \
             rl!(`{vault_uri}`, *vCh) | for (VaultBook <- vCh) {{ \
             VaultBook!(\"repay\", ownerId, auth, payment, *rCh) | \
             for (@r <- rCh) {{ match r {{ \
               (true, summary) => {{ deployId!((true, summary)) }} \
               _ => {{ deployId!(r) }} }} }} }} }} }} _ => {{ deployId!(z) }} }} }}",
            currency_lit = terms::s(currency)?,
            amount = amount,
            vault_uri = vault_uri,
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        let summary = map_at(&values, 0)?;
        field_int(summary, "debt")
    }

    /// Withdraw REV collateral from the vault into the account.
    pub async fn v4_vault_withdraw(&self, vault_uri: &str, amount: i64) -> Result<i64, ChainError> {
        let body = format!(
            "new zCh, vCh, wCh, dCh in {{ \
             @account!(\"vaultOpen\", *deployerId, `{vault_uri}`, *zCh) | \
             for (@z <- zCh) {{ match z {{ (true, auth) => {{ \
             rl!(`{vault_uri}`, *vCh) | for (VaultBook <- vCh) {{ \
             VaultBook!(\"withdraw\", ownerId, auth, {amount}, *wCh) | \
             for (@w <- wCh) {{ match w {{ \
               (true, payment) => {{ \
                 @account!(\"deposit\", *deployerId, \"REV\", payment, *dCh) | \
                 for (@_ <- dCh) {{ deployId!((true, {amount})) }} }} \
               _ => {{ deployId!(w) }} }} }} }} }} _ => {{ deployId!(z) }} }} }} }}"
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }
}
