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
    pub kind: String,
    pub stablecoin_uri: String,
    pub custody_uri: String,
    pub params_uri: String,
    pub vault_uri: String,
    pub liquidation_uri: String,
    pub savings_uri: String,
    pub psm_uri: String,
    pub buffer_uri: String,
    pub params_hash: String,
    pub sponsor: String,
    pub status: String,
    pub asset_uri: Option<String>,
    pub decimals: i64,
    pub chain: Option<String>,
    pub custodian: Option<String>,
}

/// A market record from the index.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4Market {
    pub market_id: String,
    pub slug: String,
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
    pub memo: String,
    pub op_id: String,
    pub stipend: i64,
}

/// A pool quote.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4Quote {
    pub amount_out: i64,
    pub fee: i64,
    pub rate: i64,
}

/// The seed lock's state.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4Lock {
    pub funded: bool,
    pub released: bool,
    pub cancelled: bool,
    pub until_height: i64,
    pub shares: i64,
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

/// A vault's live position.
#[derive(Clone, Debug, PartialEq)]
pub struct V4Vault {
    pub owner_id: String,
    pub collateral: i64,
    pub debt: i64,
    pub stored_debt: i64,
    pub accrued_interest: i64,
    pub last_height: i64,
    pub health: bool,
    pub fresh: bool,
    pub rate: i64,
}

/// The issuer's accounting totals.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4Totals {
    pub total_debt: i64,
    pub total_accrued_interest: i64,
    pub total_collateral: i64,
    pub bad_debt: i64,
    pub sin: i64,
    pub psm_debt: i64,
    pub paused: bool,
    pub rev: i64,
}

/// Savings-pool state.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4SavingsInfo {
    pub total_shares: i64,
    pub total_assets: i64,
    pub share_value_e8: i64,
    pub rev: i64,
}

/// A saver's position.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4SavingsPosition {
    pub shares: i64,
}

/// PSM state.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4PsmInfo {
    pub stable_debt: i64,
    pub fee_bps: i64,
    pub ceiling: i64,
    pub rev_balance: i64,
    pub rev: i64,
}

/// Surplus-buffer state.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4BufferInfo {
    pub surplus: i64,
    pub sin: i64,
    pub savings_share_bps: i64,
    pub rev: i64,
}

/// Risk-parameter state at the genesis and current hashes.
#[derive(Clone, Debug, PartialEq)]
pub struct V4RiskParams {
    pub params: BTreeMap<String, RhoValue>,
    pub genesis: BTreeMap<String, RhoValue>,
    pub params_hash: String,
    pub current_hash: String,
    pub rev: i64,
}

/// A market's canonical terms record.
#[derive(Clone, Debug, PartialEq)]
pub struct V4Terms {
    pub terms: BTreeMap<String, RhoValue>,
    pub values: Vec<String>,
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

fn field_str_opt(map: &BTreeMap<String, RhoValue>, key: &str) -> Option<String> {
    map.get(key)
        .and_then(|value| value.as_str())
        .map(str::to_string)
}

fn field_int_opt(map: &BTreeMap<String, RhoValue>, key: &str) -> Option<i64> {
    map.get(key).and_then(|value| value.as_int())
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
            kind: field_str_opt(entry, "kind").unwrap_or_else(|| "stablecoin".into()),
            stablecoin_uri: field_str_opt(entry, "stablecoinUri").unwrap_or_default(),
            custody_uri: field_str_opt(entry, "custodyUri").unwrap_or_default(),
            params_uri: field_str_opt(entry, "paramsUri").unwrap_or_default(),
            vault_uri: field_str_opt(entry, "vaultUri").unwrap_or_default(),
            liquidation_uri: field_str_opt(entry, "liquidationUri").unwrap_or_default(),
            savings_uri: field_str_opt(entry, "savingsUri").unwrap_or_default(),
            psm_uri: field_str_opt(entry, "psmUri").unwrap_or_default(),
            buffer_uri: field_str_opt(entry, "bufferUri").unwrap_or_default(),
            params_hash: field_str_opt(entry, "paramsHash").unwrap_or_default(),
            sponsor: field_str_opt(entry, "sponsor").unwrap_or_default(),
            status: field_str_opt(entry, "status").unwrap_or_default(),
            asset_uri: field_str_opt(entry, "assetUri"),
            decimals: field_int_opt(entry, "decimals").unwrap_or(8),
            chain: field_str_opt(entry, "chain"),
            custodian: field_str_opt(entry, "custodian"),
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
                    slug: field_str(entry, "slug")?,
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

    /// Activate a staged market after it is seeded and its lock is funded.
    pub async fn v4_activate(&self, market_id: &str) -> Result<String, ChainError> {
        let index = self.require_v4()?.market_index_uri.as_str().to_string();
        let term = format!(
            "new rl(`rho:registry:lookup`), ch, r, deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{index}`, *ch) | for (MarketIndex <- ch) {{ \
             MarketIndex!(\"activate\", {}, *r) | \
             for (@x <- r) {{ deployId!(x) }} }} }}",
            terms::s(market_id)?
        );
        let value = self.signed_value(&term).await?;
        match Reply::from_value(&value)? {
            Reply::Ok(values) => str_at(&values, 0),
            Reply::Refused(reason) => Err(ChainError::Refused(reason)),
        }
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

    /// A pool quote for a direction and input amount.
    pub async fn v4_quote(
        &self,
        pool_uri: &str,
        direction: &str,
        amount: i64,
    ) -> Result<V4Quote, ChainError> {
        let term = format!(
            "new rl(`rho:registry:lookup`), capCh, resCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{pool_uri}`, *capCh) | for (FxPool <- capCh) {{ \
             FxPool!(\"quote\", {}, {amount}, *resCh) | \
             for (@r <- resCh) {{ deployId!(r) }} }} }}",
            terms::s(direction)?
        );
        let value = self.signed_value(&term).await?;
        let values = Reply::from_value(&value)?.into_result()?;
        Ok(V4Quote {
            amount_out: int_at(&values, 0)?,
            fee: int_at(&values, 1)?,
            rate: int_at(&values, 2)?,
        })
    }

    /// The seed lock's state.
    pub async fn v4_lock_info(&self, lock_uri: &str) -> Result<V4Lock, ChainError> {
        let reply = self.v4_read(lock_uri, "\"info\"").await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        Ok(V4Lock {
            funded: field(entry, "funded")?
                .as_bool()
                .ok_or_else(|| decode("funded is not a boolean"))?,
            released: field(entry, "released")?
                .as_bool()
                .ok_or_else(|| decode("released is not a boolean"))?,
            cancelled: field(entry, "cancelled")?
                .as_bool()
                .ok_or_else(|| decode("cancelled is not a boolean"))?,
            until_height: field_int(entry, "untilHeight")?,
            shares: field_int(entry, "shares")?,
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
            memo: field_str(entry, "memo")?,
            op_id: field_str(entry, "opId")?,
            stipend: field_int(entry, "stipend")?,
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
    #[allow(clippy::too_many_arguments)]
    pub async fn v4_send_transfer(
        &self,
        recipient_pub_hex: &str,
        asset: &str,
        amount: i64,
        secret_hash_hex: &str,
        expiry: i64,
        memo: &str,
        op_id: &str,
        stipend: i64,
    ) -> Result<V4Sent, ChainError> {
        if amount <= 0 {
            return Err(decode("amount must be positive"));
        }
        if stipend < 0 {
            return Err(decode("stipend must be non-negative"));
        }
        if memo.len() > 128 {
            return Err(decode("memo exceeds 128 bytes"));
        }
        if op_id.len() > 64 {
            return Err(decode("opId exceeds 64 bytes"));
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
                 @account!(\"sendTransfer\", *deployerId, {asset_lit}, facet, \
                           \"{recipient_pub_hex}\".hexToBytes(), {amount}, \
                           {hash}, {expiry}, {memo_lit}, {op_id_lit}, {stipend}, *sCh) | \
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
            memo_lit = terms::s(memo)?,
            op_id_lit = terms::s(op_id)?,
            stipend = stipend,
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
        // Preflight the feed so a stale oracle is refused before the account withdraws.
        self.v4_quote(pool_uri, direction, 1).await?;
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
               _ => {{ deployId!(1 / 0) }} }} }} }} }} }}",
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
        min_base: i64,
        min_quote: i64,
    ) -> Result<i64, ChainError> {
        if min_base < 0 || min_quote < 0 {
            return Err(decode("minimums must be non-negative"));
        }
        let body = format!(
            "new lCh, rCh, pCh, rrCh, d1, d2 in {{ \
             rl!(`{lock_uri}`, *lCh) | for (LiquidityLock <- lCh) {{ \
             LiquidityLock!(\"release\", *deployerId, *rCh) | \
             for (@r <- rCh) {{ match r {{ \
               (true, lpPayment, shares) => {{ \
                 rl!(`{pool_uri}`, *pCh) | for (FxPool <- pCh) {{ \
                 FxPool!(\"removeLiquidity\", lpPayment, {min_base}, {min_quote}, *rrCh) | \
                 for (@rr <- rrCh) {{ match rr {{ \
                   (true, basePayment, quotePayment) => {{ \
                     @account!(\"deposit\", *deployerId, {base_lit}, basePayment, *d1) | \
                     @account!(\"deposit\", *deployerId, {quote_lit}, quotePayment, *d2) | \
                     for (@_ <- d1; @_ <- d2) {{ deployId!((true, shares)) }} }} \
                   _ => {{ deployId!(1 / 0) }} }} }} }} }} \
               _ => {{ deployId!(1 / 0) }} }} }} }} }}",
            base_lit = terms::s(base_asset)?,
            quote_lit = terms::s(quote_asset)?,
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }

    /// Add both sides of a market from the account and lock the seed LP.
    #[allow(clippy::too_many_arguments)]
    pub async fn v4_add_liquidity(
        &self,
        pool_uri: &str,
        lock_uri: &str,
        base_asset: &str,
        quote_asset: &str,
        base_amount: i64,
        quote_amount: i64,
        until_height: i64,
        min_shares: i64,
    ) -> Result<i64, ChainError> {
        if min_shares < 0 {
            return Err(decode("minimum shares must be non-negative"));
        }
        // Preflight the feed before either side leaves the account.
        self.v4_quote(pool_uri, "b2q", 1).await?;
        // A funded lock refuses the funding step after the pool has already minted the
        // LP. Check before withdrawing either side, so a retry cannot strand the seed.
        let lock_state = self.v4_lock_info(lock_uri).await?;
        if lock_state.funded || lock_state.released || lock_state.cancelled {
            return Err(ChainError::Refused(
                "seed lock is already funded or closed".into(),
            ));
        }
        let body = format!(
            "new wb, wq, pCh, aCh, lCh, fCh, rCh, rb, db, dq in {{ \
             @account!(\"withdraw\", *deployerId, {base_lit}, {base_amount}, *wb) | \
             for (@(true, basePayment) <- wb) {{ \
               @account!(\"withdraw\", *deployerId, {quote_lit}, {quote_amount}, *wq) | \
               for (@(true, quotePayment) <- wq) {{ \
                 rl!(`{pool_uri}`, *pCh) | for (FxPool <- pCh) {{ \
                 FxPool!(\"addLiquidity\", basePayment, quotePayment, {min_shares}, *aCh) | \
                 for (@a <- aCh) {{ match a {{ \
                   (true, lpPayment, shares) => {{ \
                     rl!(`{lock_uri}`, *lCh) | for (LiquidityLock <- lCh) {{ \
                     LiquidityLock!(\"fund\", *deployerId, lpPayment, ownerId, \
                                   {until_height}, *fCh) | \
                     for (@f <- fCh) {{ match f {{ \
                       (true, _) => deployId!((true, shares)) \
                       (false, reason, lpPayment) => {{ \
                         rl!(`{pool_uri}`, *rCh) | for (FxPool2 <- rCh) {{ \
                         FxPool2!(\"removeLiquidity\", lpPayment, 0, 0, *rb) | \
                         for (@rr2 <- rb) {{ match rr2 {{ \
                           (true, baseBack, quoteBack) => {{ \
                             @account!(\"deposit\", *deployerId, {base_lit}, baseBack, *db) | \
                             @account!(\"deposit\", *deployerId, {quote_lit}, quoteBack, *dq) | \
                             for (@_ <- db; @_ <- dq) {{ deployId!((false, reason)) }} }} \
                           _ => deployId!((false, reason)) }} }} }} }} \
                       _ => deployId!(f) }} }} }} }} \
                   _ => deployId!(1 / 0) }} }} }} }} }} }}",
            base_lit = terms::s(base_asset)?,
            quote_lit = terms::s(quote_asset)?,
            base_amount = base_amount,
            quote_amount = quote_amount,
            until_height = until_height,
            pool_uri = pool_uri,
            lock_uri = lock_uri,
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
                 _ => {{ deployId!(1 / 0) }} }} }} }} _ => {{ deployId!(1 / 0) }} }} }} \
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
               _ => {{ deployId!(1 / 0) }} }} }} }} }} }} _ => {{ deployId!(z) }} }} }}",
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
               _ => {{ deployId!(1 / 0) }} }} }} }} }} _ => {{ deployId!(z) }} }} }} }}"
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }
}

// ---- v0.5 surface: vaults, savings, PSM, discovery -------------------------

fn field_bool(map: &BTreeMap<String, RhoValue>, key: &str) -> Result<bool, ChainError> {
    field(map, key)?
        .as_bool()
        .ok_or_else(|| decode(format!("field {key} is not a boolean")))
}

fn currency_from_entry(
    code: &str,
    entry: &BTreeMap<String, RhoValue>,
) -> Result<V4Currency, ChainError> {
    Ok(V4Currency {
        code: code.to_string(),
        kind: field_str_opt(entry, "kind").unwrap_or_else(|| "stablecoin".into()),
        stablecoin_uri: field_str_opt(entry, "stablecoinUri").unwrap_or_default(),
        custody_uri: field_str_opt(entry, "custodyUri").unwrap_or_default(),
        params_uri: field_str_opt(entry, "paramsUri").unwrap_or_default(),
        vault_uri: field_str_opt(entry, "vaultUri").unwrap_or_default(),
        liquidation_uri: field_str_opt(entry, "liquidationUri").unwrap_or_default(),
        savings_uri: field_str_opt(entry, "savingsUri").unwrap_or_default(),
        psm_uri: field_str_opt(entry, "psmUri").unwrap_or_default(),
        buffer_uri: field_str_opt(entry, "bufferUri").unwrap_or_default(),
        params_hash: field_str_opt(entry, "paramsHash").unwrap_or_default(),
        sponsor: field_str_opt(entry, "sponsor").unwrap_or_default(),
        status: field_str_opt(entry, "status").unwrap_or_default(),
        asset_uri: field_str_opt(entry, "assetUri"),
        decimals: field_int_opt(entry, "decimals").unwrap_or(8),
        chain: field_str_opt(entry, "chain"),
        custodian: field_str_opt(entry, "custodian"),
    })
}

fn market_from_entry(entry: &BTreeMap<String, RhoValue>) -> Result<V4Market, ChainError> {
    Ok(V4Market {
        market_id: field_str(entry, "marketId")?,
        slug: field_str(entry, "slug")?,
        base: field_str(entry, "base")?,
        quote: field_str(entry, "quote")?,
        version: field_int(entry, "version")?,
        terms_hash: field_str(entry, "termsHash")?,
        status: field_str(entry, "status")?,
    })
}

impl Client {
    async fn v4_signed_read(&self, uri: &str, args: &str) -> Result<Reply, ChainError> {
        let term = format!(
            "new rl(`rho:registry:lookup`), capCh, resCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{uri}`, *capCh) | for (cap <- capCh) {{ \
             cap!({args}, *resCh) | for (@r <- resCh) {{ deployId!(r) }} }} }}"
        );
        let value = self.signed_value(&term).await?;
        Reply::from_value(&value)
    }

    /// Every listed currency, discovered through `ListingViews.currencies`.
    pub async fn v4_currencies(&self) -> Result<Vec<V4Currency>, ChainError> {
        let views = self.require_v4()?.listing_views_uri.as_str().to_string();
        let reply = self.v4_read(&views, "\"currencies\"").await?;
        let values = reply.into_result()?;
        let entries = map_at(&values, 0)?;
        let mut out = Vec::new();
        for (code, entry) in entries {
            match entry.as_map() {
                Some(map) => out.push(currency_from_entry(code, map)?),
                None => return Err(decode("currency entry is not a map")),
            }
        }
        Ok(out)
    }

    /// Every staged or listed market.
    pub async fn v4_markets(&self) -> Result<Vec<V4Market>, ChainError> {
        let views = self.require_v4()?.listing_views_uri.as_str().to_string();
        let reply = self.v4_read(&views, "\"markets\"").await?;
        let values = reply.into_result()?;
        let entries = map_at(&values, 0)?;
        let mut out = Vec::new();
        for entry in entries.values() {
            match entry.as_map() {
                Some(map) => out.push(market_from_entry(map)?),
                None => return Err(decode("market entry is not a map")),
            }
        }
        Ok(out)
    }

    /// A market's canonical terms record.
    pub async fn v4_terms(&self, terms_hash: &str) -> Result<V4Terms, ChainError> {
        let views = self.require_v4()?.listing_views_uri.as_str().to_string();
        let reply = self
            .v4_read(&views, &format!("\"terms\", {}", terms::s(terms_hash)?))
            .await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        let terms = field(entry, "terms")?
            .as_map()
            .ok_or_else(|| decode("terms is not a map"))?
            .clone();
        let raw_values = field(entry, "values")?
            .as_list()
            .ok_or_else(|| decode("values is not a list"))?;
        let mut list = Vec::with_capacity(raw_values.len());
        for value in raw_values {
            list.push(
                value
                    .as_str()
                    .ok_or_else(|| decode("term value is not a string"))?
                    .to_string(),
            );
        }
        Ok(V4Terms {
            terms,
            values: list,
        })
    }

    /// The caller's live vault position, accrual included.
    pub async fn v4_vault(&self, vault_uri: &str) -> Result<V4Vault, ChainError> {
        let owner = self.address()?;
        let reply = self
            .v4_signed_read(vault_uri, &format!("\"vault\", {}", terms::s(&owner)?))
            .await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        Ok(V4Vault {
            owner_id: field_str(entry, "ownerId")?,
            collateral: field_int(entry, "collateral")?,
            debt: field_int(entry, "debt")?,
            stored_debt: field_int(entry, "storedDebt")?,
            accrued_interest: field_int(entry, "accruedInterest")?,
            last_height: field_int(entry, "lastHeight")?,
            health: field_bool(entry, "health")?,
            fresh: field_bool(entry, "fresh")?,
            rate: field_int(entry, "rate")?,
        })
    }

    /// The issuer's accounting totals.
    pub async fn v4_totals(&self, vault_uri: &str) -> Result<V4Totals, ChainError> {
        let reply = self.v4_read(vault_uri, "\"totals\"").await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        Ok(V4Totals {
            total_debt: field_int(entry, "totalDebt")?,
            total_accrued_interest: field_int(entry, "totalAccruedInterest")?,
            total_collateral: field_int(entry, "totalCollateral")?,
            bad_debt: field_int(entry, "badDebt")?,
            sin: field_int(entry, "sin")?,
            psm_debt: field_int(entry, "psmDebt")?,
            paused: field_bool(entry, "paused")?,
            rev: field_int(entry, "rev")?,
        })
    }

    /// Savings-pool state.
    pub async fn v4_savings_info(&self, savings_uri: &str) -> Result<V4SavingsInfo, ChainError> {
        let reply = self.v4_read(savings_uri, "\"info\"").await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        Ok(V4SavingsInfo {
            total_shares: field_int(entry, "totalShares")?,
            total_assets: field_int(entry, "totalAssets")?,
            share_value_e8: field_int(entry, "shareValueE8")?,
            rev: field_int(entry, "rev")?,
        })
    }

    /// The caller's savings position.
    pub async fn v4_savings_position(
        &self,
        savings_uri: &str,
    ) -> Result<V4SavingsPosition, ChainError> {
        let owner = self.address()?;
        let reply = self
            .v4_signed_read(savings_uri, &format!("\"position\", {}", terms::s(&owner)?))
            .await?;
        let values = reply.into_result()?;
        Ok(V4SavingsPosition {
            shares: int_at(&values, 0)?,
        })
    }

    /// PSM state, including the signed debt and REV balance.
    pub async fn v4_psm_info(&self, psm_uri: &str) -> Result<V4PsmInfo, ChainError> {
        let reply = self.v4_read(psm_uri, "\"info\"").await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        Ok(V4PsmInfo {
            stable_debt: field_int(entry, "stableDebt")?,
            fee_bps: field_int(entry, "feeBps")?,
            ceiling: field_int(entry, "ceiling")?,
            rev_balance: field_int(entry, "revBalance")?,
            rev: field_int(entry, "rev")?,
        })
    }

    /// Surplus-buffer state.
    pub async fn v4_buffer_info(&self, buffer_uri: &str) -> Result<V4BufferInfo, ChainError> {
        let reply = self.v4_read(buffer_uri, "\"info\"").await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        Ok(V4BufferInfo {
            surplus: field_int(entry, "surplus")?,
            sin: field_int(entry, "sin")?,
            savings_share_bps: field_int(entry, "savingsShareBps")?,
            rev: field_int(entry, "rev")?,
        })
    }

    /// Risk parameters with both the genesis and current hashes.
    pub async fn v4_risk_params(&self, params_uri: &str) -> Result<V4RiskParams, ChainError> {
        let reply = self.v4_read(params_uri, "\"info\"").await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        Ok(V4RiskParams {
            params: field(entry, "params")?
                .as_map()
                .ok_or_else(|| decode("params is not a map"))?
                .clone(),
            genesis: field(entry, "genesis")?
                .as_map()
                .ok_or_else(|| decode("genesis is not a map"))?
                .clone(),
            params_hash: field_str(entry, "paramsHash")?,
            current_hash: field_str(entry, "currentHash")?,
            rev: field_int(entry, "rev")?,
        })
    }

    /// The caller's transfer op ledger.
    pub async fn v4_transfers(&self) -> Result<BTreeMap<String, RhoValue>, ChainError> {
        let body = "new r in { @account!(\"transfers\", *deployerId, *r) | \
                    for (@x <- r) { deployId!(x) } }";
        let values = self.v4_tx(body).await?.into_result()?;
        values
            .first()
            .and_then(RhoValue::as_map)
            .cloned()
            .ok_or_else(|| decode("transfers did not return a map"))
    }

    // ---- vault writes -------------------------------------------------------

    /// Open (or reuse) the caller's vault.
    pub async fn v4_vault_open(&self, vault_uri: &str) -> Result<(), ChainError> {
        let body = format!(
            "new zCh in {{ @account!(\"vaultOpen\", *deployerId, `{vault_uri}`, *zCh) | \
             for (@z <- zCh) {{ match z {{ (true, _) => deployId!((true, Nil)) \
             _ => deployId!(z) }} }} }}"
        );
        self.v4_tx(&body).await?.into_result()?;
        Ok(())
    }

    /// Deposit REV collateral into the caller's vault.
    pub async fn v4_vault_deposit(&self, vault_uri: &str, amount: i64) -> Result<i64, ChainError> {
        if amount <= 0 {
            return Err(decode("amount must be positive"));
        }
        let body = format!(
            "new zCh, wCh, vCh, dCh in {{ \
             @account!(\"vaultOpen\", *deployerId, `{vault_uri}`, *zCh) | \
             for (@z <- zCh) {{ match z {{ (true, auth) => {{ \
             @account!(\"withdraw\", *deployerId, \"REV\", {amount}, *wCh) | \
             for (@(true, payment) <- wCh) {{ \
             rl!(`{vault_uri}`, *vCh) | for (VaultBook <- vCh) {{ \
             VaultBook!(\"deposit\", ownerId, auth, payment, *dCh) | \
             for (@d <- dCh) {{ match d {{ (true, summary) => deployId!((true, summary)) \
             _ => deployId!(1 / 0) }} }} }} }} _ => deployId!(z) }} }} }}"
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        let summary = map_at(&values, 0)?;
        field_int(summary, "collateral")
    }

    /// Liquidate an unhealthy vault and deposit the seized REV into the account.
    pub async fn v4_vault_liquidate(
        &self,
        liquidation_uri: &str,
        currency: &str,
        owner_id: &str,
        amount: i64,
        min_collateral: i64,
    ) -> Result<i64, ChainError> {
        if amount <= 0 {
            return Err(decode("amount must be positive"));
        }
        let body = format!(
            "new wCh, vCh, lrCh, dCh in {{ \
             @account!(\"withdraw\", *deployerId, {currency_lit}, {amount}, *wCh) | \
             for (@(true, payment) <- wCh) {{ \
             rl!(`{liquidation_uri}`, *vCh) | for (LiquidationEngine <- vCh) {{ \
             LiquidationEngine!(\"liquidate\", {owner_lit}, payment, {min_collateral}, *lrCh) | \
             for (@lr <- lrCh) {{ match lr {{ \
               (true, revPayment, summary) => {{ \
                 @account!(\"deposit\", *deployerId, \"REV\", revPayment, *dCh) | \
                 for (@_ <- dCh) {{ match summary {{ m => deployId!((true, m)) }} }} }} \
               _ => deployId!(1 / 0) }} }} }} }} }}",
            currency_lit = terms::s(currency)?,
            owner_lit = terms::s(owner_id)?,
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        let summary = map_at(&values, 0)?;
        field_int(summary, "seized")
    }

    // ---- savings writes -----------------------------------------------------

    /// Deposit stablecoin into the savings pool; returns shares.
    pub async fn v4_savings_deposit(
        &self,
        savings_uri: &str,
        currency: &str,
        amount: i64,
    ) -> Result<i64, ChainError> {
        if amount <= 0 {
            return Err(decode("amount must be positive"));
        }
        let body = format!(
            "new wCh, sCh, dCh in {{ \
             @account!(\"withdraw\", *deployerId, {currency_lit}, {amount}, *wCh) | \
             for (@(true, payment) <- wCh) {{ \
             rl!(`{savings_uri}`, *sCh) | for (SavingsPool <- sCh) {{ \
             SavingsPool!(\"deposit\", *deployerId, payment, *dCh) | \
             for (@d <- dCh) {{ match d {{ (true, shares) => deployId!((true, shares)) \
             _ => deployId!(1 / 0) }} }} }} }} }}",
            currency_lit = terms::s(currency)?,
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }

    /// Withdraw savings shares; returns the stablecoin amount.
    pub async fn v4_savings_withdraw(
        &self,
        savings_uri: &str,
        currency: &str,
        shares: i64,
    ) -> Result<i64, ChainError> {
        if shares <= 0 {
            return Err(decode("shares must be positive"));
        }
        let body = format!(
            "new sCh, dCh in {{ \
             rl!(`{savings_uri}`, *sCh) | for (SavingsPool <- sCh) {{ \
             SavingsPool!(\"withdraw\", *deployerId, {shares}, *dCh) | \
             for (@d <- dCh) {{ match d {{ \
               (true, payment, amount) => {{ \
                 @account!(\"deposit\", *deployerId, {currency_lit}, payment, *dCh) | \
                 for (@_ <- dCh) {{ deployId!((true, amount)) }} }} \
               _ => deployId!(1 / 0) }} }} }} }}",
            currency_lit = terms::s(currency)?,
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }

    // ---- PSM writes ---------------------------------------------------------

    /// Redeem stablecoin for REV at par minus the fee.
    pub async fn v4_psm_sell(
        &self,
        psm_uri: &str,
        currency: &str,
        amount: i64,
        min_rev: i64,
    ) -> Result<i64, ChainError> {
        if amount <= 0 {
            return Err(decode("amount must be positive"));
        }
        let body = format!(
            "new wCh, fCh, pCh, rCh in {{ \
             @account!(\"depositFacet\", \"REV\", *fCh) | \
             for (@f <- fCh) {{ match f {{ (true, revFacet) => {{ \
             @account!(\"withdraw\", *deployerId, {currency_lit}, {amount}, *wCh) | \
             for (@(true, payment) <- wCh) {{ \
             rl!(`{psm_uri}`, *pCh) | for (PegStabilityModule <- pCh) {{ \
             PegStabilityModule!(\"sellStable\", payment, revFacet, {min_rev}, *rCh) | \
             for (@r <- rCh) {{ match r {{ (true, revOut, fee) => deployId!((true, revOut)) \
             _ => deployId!(1 / 0) }} }} }} }} }} _ => deployId!(f) }} }} }}",
            currency_lit = terms::s(currency)?,
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }

    /// Mint stablecoin against REV at par minus the fee.
    pub async fn v4_psm_buy(
        &self,
        psm_uri: &str,
        currency: &str,
        rev_amount: i64,
        min_stable: i64,
    ) -> Result<i64, ChainError> {
        if rev_amount <= 0 {
            return Err(decode("rev amount must be positive"));
        }
        let body = format!(
            "new wCh, fCh, pCh, rCh, dCh in {{ \
             @account!(\"depositFacet\", {currency_lit}, *fCh) | \
             for (@f <- fCh) {{ match f {{ (true, stableFacet) => {{ \
             @account!(\"withdraw\", *deployerId, \"REV\", {rev_amount}, *wCh) | \
             for (@(true, payment) <- wCh) {{ \
             rl!(`{psm_uri}`, *pCh) | for (PegStabilityModule <- pCh) {{ \
             PegStabilityModule!(\"buyStable\", payment, stableFacet, {min_stable}, *rCh) | \
             for (@r <- rCh) {{ match r {{ (true, stableOut, fee) => \
             deployId!((true, stableOut)) _ => deployId!(1 / 0) }} }} }} }} }} \
             _ => deployId!(f) }} }} }}",
            currency_lit = terms::s(currency)?,
        );
        let values = self.v4_tx(&body).await?.into_result()?;
        int_at(&values, 0)
    }
}

// ---- governance and market writes ------------------------------------------

/// The issuer parameters accepted by a governed risk-parameter change.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4IssuerParams {
    pub mcr_bps: i64,
    pub bonus_bps: i64,
    pub close_factor_bps: i64,
    pub rate_per_block: i64,
    pub debt_ceiling: i64,
    pub min_debt: i64,
    pub max_debt: i64,
    pub max_oracle_age: i64,
    pub savings_share_bps: i64,
    pub psm_fee_bps: i64,
}

/// A market created by this client.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4CreatedMarket {
    pub market_id: String,
    pub pool_uri: String,
    pub lock_uri: String,
    pub terms_hash: String,
}

/// A scheduled governance action.
#[derive(Clone, Debug, PartialEq)]
pub struct V4Pending {
    pub action: String,
    pub args_hash: String,
    pub args: RhoValue,
    pub ready_at: i64,
}

fn render_sigs(sigs: &[String]) -> Result<String, ChainError> {
    let parts: Result<Vec<String>, rcash_core::CoreError> = sigs
        .iter()
        .map(|sig| rcash_core::rho::hex_bytes(sig))
        .collect();
    Ok(format!("[{}]", parts?.join(", ")))
}

fn render_issuer_params(p: &V4IssuerParams) -> String {
    format!(
        "{{\"mcrBps\": {}, \"bonusBps\": {}, \"closeFactorBps\": {}, \
          \"ratePerBlock\": {}, \"debtCeiling\": {}, \"minDebt\": {}, \
          \"maxDebt\": {}, \"maxOracleAge\": {}, \"savingsShareBps\": {}, \
          \"psmFeeBps\": {}}}",
        p.mcr_bps,
        p.bonus_bps,
        p.close_factor_bps,
        p.rate_per_block,
        p.debt_ceiling,
        p.min_debt,
        p.max_debt,
        p.max_oracle_age,
        p.savings_share_bps,
        p.psm_fee_bps,
    )
}

fn render_terms(t: &rcash_core::market::MarketTerms) -> Result<(String, String), ChainError> {
    let map = format!(
        "{{\"marketId\": {}, \"slug\": {}, \"base\": {}, \"quote\": {}, \
          \"version\": {}, \"sponsorPubKey\": {}, \"sponsorOwnerId\": {}, \
          \"baseFeedPolicyHash\": {}, \"quoteFeedPolicyHash\": {}, \
          \"baseSpreadBps\": {}, \"skewSpreadBps\": {}, \"maxTradeBps\": {}, \
          \"minLiquidity\": {}, \"firstDepositToleranceBps\": {}, \
          \"depthFloorQuote\": {}, \"minTicketQuote\": {}, \"seedBase\": {}, \
          \"seedQuote\": {}, \"seedInitialShares\": {}, \
          \"lockBeneficiaryPubKey\": {}, \"lockMinBlocks\": {}, \
          \"lockUntilHeight\": {}, \"bookDefaultExpiryBlocks\": {}, \
          \"bookMaxExpiryBlocks\": {}, \"maxPairAgeBlocks\": {}}}",
        terms::s(&t.market_id)?,
        terms::s(&t.slug)?,
        terms::s(&t.base.to_string())?,
        terms::s(&t.quote.to_string())?,
        t.version,
        terms::s(&t.sponsor_pub_key)?,
        terms::s(&t.sponsor_owner_id)?,
        terms::s(&t.base_feed_policy_hash)?,
        terms::s(&t.quote_feed_policy_hash)?,
        t.base_spread_bps,
        t.skew_spread_bps,
        t.max_trade_bps,
        t.min_liquidity,
        t.first_deposit_tolerance_bps,
        t.depth_floor_quote,
        t.min_ticket_quote,
        t.seed_base,
        t.seed_quote,
        t.seed_initial_shares,
        terms::s(&t.lock_beneficiary_pub_key)?,
        t.lock_min_blocks,
        t.lock_until_height,
        t.book_default_expiry_blocks,
        t.book_max_expiry_blocks,
        t.max_pair_age_blocks,
    );
    let values: Result<Vec<String>, rcash_core::CoreError> =
        t.values().iter().map(|v| terms::s(v)).collect();
    Ok((map, format!("[{}]", values?.join(", "))))
}

impl Client {
    /// Create a market. The client signs the sponsor payload with its own key.
    pub async fn v4_create_market(
        &self,
        terms: &rcash_core::market::MarketTerms,
    ) -> Result<V4CreatedMarket, ChainError> {
        use rcash_chain::sign_payload_hex;
        let key = self
            .key()
            .ok_or_else(|| ChainError::BadKey("market creation needs a signing key".into()))?;
        let sponsor = key.public_hex();
        let terms_hash = terms.canonical();
        let payload = format!(
            "rcash:market-create:v1|{}|{}|{}",
            terms.market_id, terms_hash, sponsor
        );
        let sig = sign_payload_hex(key, payload.as_bytes())?;
        let (map, values) = render_terms(terms)?;
        let factory = self.require_v4()?.market_factory_uri.as_str().to_string();
        let term = format!(
            "new rl(`rho:registry:lookup`), fCh, rCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{factory}`, *fCh) | for (MarketFactory <- fCh) {{ \
             MarketFactory!(\"createMarket\", {map}, {values}, {sponsor_lit}, \
                            \"{sig}\".hexToBytes(), *rCh) | \
             for (@r <- rCh) {{ deployId!(r) }} }} }}",
            sponsor_lit = terms::s(&sponsor)?,
        );
        let value = self.signed_value(&term).await?;
        let values = Reply::from_value(&value)?.into_result()?;
        Ok(V4CreatedMarket {
            market_id: str_at(&values, 0)?,
            pool_uri: str_at(&values, 1)?,
            lock_uri: str_at(&values, 2)?,
            terms_hash: str_at(&values, 3)?,
        })
    }

    /// Change a market's status with governor signatures.
    pub async fn v4_set_market_status(
        &self,
        market_id: &str,
        status: &str,
        nonce: i64,
        sigs: &[String],
    ) -> Result<(), ChainError> {
        let index = self.require_v4()?.market_index_uri.as_str().to_string();
        let term = format!(
            "new rl(`rho:registry:lookup`), cCh, rCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{index}`, *cCh) | for (MarketIndex <- cCh) {{ \
             MarketIndex!(\"setStatus\", {}, {}, {nonce}, {sigs}, *rCh) | \
             for (@r <- rCh) {{ deployId!(r) }} }} }}",
            terms::s(market_id)?,
            terms::s(status)?,
            sigs = render_sigs(sigs)?,
        );
        let value = self.signed_value(&term).await?;
        Reply::from_value(&value)?.into_result()?;
        Ok(())
    }

    /// Pause or resume a currency with governor signatures.
    pub async fn v4_pause_currency(
        &self,
        code: &str,
        paused: bool,
        nonce: i64,
        sigs: &[String],
    ) -> Result<(), ChainError> {
        let registry = self
            .require_v4()?
            .currency_registry_uri
            .as_str()
            .to_string();
        let term = format!(
            "new rl(`rho:registry:lookup`), cCh, rCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{registry}`, *cCh) | for (CurrencyRegistry <- cCh) {{ \
             CurrencyRegistry!(\"setPaused\", {}, {paused}, {nonce}, {sigs}, *rCh) | \
             for (@r <- rCh) {{ deployId!(r) }} }} }}",
            terms::s(code)?,
            paused = paused,
            sigs = render_sigs(sigs)?,
        );
        let value = self.signed_value(&term).await?;
        Reply::from_value(&value)?.into_result()?;
        Ok(())
    }

    /// Schedule a risk-parameter change (timelocked).
    pub async fn v4_schedule_risk_params(
        &self,
        params_uri: &str,
        params: &V4IssuerParams,
        nonce: i64,
        sigs: &[String],
    ) -> Result<i64, ChainError> {
        let term = format!(
            "new rl(`rho:registry:lookup`), cCh, rCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{params_uri}`, *cCh) | for (RiskParameters <- cCh) {{ \
             RiskParameters!(\"scheduleParams\", {}, {nonce}, {sigs}, *rCh) | \
             for (@r <- rCh) {{ deployId!(r) }} }} }}",
            render_issuer_params(params),
            sigs = render_sigs(sigs)?,
        );
        let value = self.signed_value(&term).await?;
        let values = Reply::from_value(&value)?.into_result()?;
        int_at(&values, 0)
    }

    /// Apply a scheduled risk-parameter change after the timelock.
    pub async fn v4_apply_risk_params(
        &self,
        params_uri: &str,
        nonce: i64,
    ) -> Result<(), ChainError> {
        let term = format!(
            "new rl(`rho:registry:lookup`), cCh, rCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{params_uri}`, *cCh) | for (RiskParameters <- cCh) {{ \
             RiskParameters!(\"applyParams\", {nonce}, *rCh) | \
             for (@r <- rCh) {{ deployId!(r) }} }} }}"
        );
        let value = self.signed_value(&term).await?;
        Reply::from_value(&value)?.into_result()?;
        Ok(())
    }

    /// Schedule a savings-share change (timelocked).
    pub async fn v4_schedule_savings_share(
        &self,
        buffer_uri: &str,
        bps: i64,
        nonce: i64,
        sigs: &[String],
    ) -> Result<i64, ChainError> {
        let term = format!(
            "new rl(`rho:registry:lookup`), cCh, rCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{buffer_uri}`, *cCh) | for (SurplusBuffer <- cCh) {{ \
             SurplusBuffer!(\"scheduleShare\", {bps}, {nonce}, {sigs}, *rCh) | \
             for (@r <- rCh) {{ deployId!(r) }} }} }}",
            sigs = render_sigs(sigs)?,
        );
        let value = self.signed_value(&term).await?;
        let values = Reply::from_value(&value)?.into_result()?;
        int_at(&values, 0)
    }

    /// Apply a scheduled savings-share change.
    pub async fn v4_apply_savings_share(
        &self,
        buffer_uri: &str,
        nonce: i64,
    ) -> Result<(), ChainError> {
        let term = format!(
            "new rl(`rho:registry:lookup`), cCh, rCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{buffer_uri}`, *cCh) | for (SurplusBuffer <- cCh) {{ \
             SurplusBuffer!(\"applyShare\", {nonce}, *rCh) | \
             for (@r <- rCh) {{ deployId!(r) }} }} }}"
        );
        let value = self.signed_value(&term).await?;
        Reply::from_value(&value)?.into_result()?;
        Ok(())
    }

    /// Schedule a PSM fee/ceiling change (timelocked).
    pub async fn v4_schedule_psm_policy(
        &self,
        psm_uri: &str,
        fee_bps: i64,
        ceiling: i64,
        nonce: i64,
        sigs: &[String],
    ) -> Result<i64, ChainError> {
        let term = format!(
            "new rl(`rho:registry:lookup`), cCh, rCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{psm_uri}`, *cCh) | for (PegStabilityModule <- cCh) {{ \
             PegStabilityModule!(\"schedulePolicy\", {fee_bps}, {ceiling}, {nonce}, {sigs}, *rCh) | \
             for (@r <- rCh) {{ deployId!(r) }} }} }}",
            sigs = render_sigs(sigs)?,
        );
        let value = self.signed_value(&term).await?;
        let values = Reply::from_value(&value)?.into_result()?;
        int_at(&values, 0)
    }

    /// Apply a scheduled PSM policy.
    pub async fn v4_apply_psm_policy(&self, psm_uri: &str, nonce: i64) -> Result<(), ChainError> {
        let term = format!(
            "new rl(`rho:registry:lookup`), cCh, rCh, \
             deployId(`rho:rchain:deployId`) in {{ \
             rl!(`{psm_uri}`, *cCh) | for (PegStabilityModule <- cCh) {{ \
             PegStabilityModule!(\"applyPolicy\", {nonce}, *rCh) | \
             for (@r <- rCh) {{ deployId!(r) }} }} }}"
        );
        let value = self.signed_value(&term).await?;
        Reply::from_value(&value)?.into_result()?;
        Ok(())
    }

    /// A scheduled governor action, if one exists.
    pub async fn v4_pending(
        &self,
        domain: &str,
        nonce: i64,
    ) -> Result<Option<V4Pending>, ChainError> {
        let governor = self.require_v4()?.governor_uri.as_str().to_string();
        let reply = self
            .v4_read(
                &governor,
                &format!("\"pending\", {}, {nonce}", terms::s(domain)?),
            )
            .await?;
        match reply {
            Reply::Refused(_) => Ok(None),
            Reply::Ok(values) => Ok(Some(V4Pending {
                action: str_at(&values, 0)?,
                args_hash: str_at(&values, 1)?,
                args: values
                    .get(2)
                    .cloned()
                    .ok_or_else(|| decode("pending args missing"))?,
                ready_at: int_at(&values, 3)?,
            })),
        }
    }
}

/// An oracle pair reading with per-feed ages.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct V4Price {
    pub rate: i64,
    pub fresh: bool,
    pub base_price: i64,
    pub quote_price: i64,
    pub base_age: i64,
    pub quote_age: i64,
}

impl Client {
    /// The hub cross-rate and feed ages for a pair.
    pub async fn v4_price(
        &self,
        base: &str,
        quote: &str,
        max_age: i64,
    ) -> Result<V4Price, ChainError> {
        let hub = self.require_v4()?.oracle_hub_uri.as_str().to_string();
        let args = format!(
            "\"getPair\", {}, {}, {max_age}",
            terms::s(base)?,
            terms::s(quote)?
        );
        let reply = self.v4_signed_read(&hub, &args).await?;
        let values = reply.into_result()?;
        let entry = map_at(&values, 0)?;
        Ok(V4Price {
            rate: field_int(entry, "rate")?,
            fresh: field_bool(entry, "fresh")?,
            base_price: field_int(entry, "basePrice")?,
            quote_price: field_int(entry, "quotePrice")?,
            base_age: field_int(entry, "baseAge")?,
            quote_age: field_int(entry, "quoteAge")?,
        })
    }

    /// The rate of `asset` in `display`, for preferred-currency display.
    /// Returns the 1e8-scaled quote-per-base rate from the oracle hub.
    pub async fn v4_price_in(&self, asset: &str, display: &str) -> Result<i64, ChainError> {
        if asset == display {
            return Ok(100_000_000);
        }
        Ok(self.v4_price(asset, display, 50).await?.rate)
    }
}
