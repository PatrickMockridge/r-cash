//! Typed protocol reads.
//!
//! Public reads use `explore-deploy` and cost no phlo, but **`explore-deploy` has no block
//! context**: `rho:block:data` reports height 0 there. Arms that check oracle freshness
//! (`oracle get`/`getPair`, `pool quote`/`quoteAdd`, `zone vault` health, `book quote`)
//! must therefore run as signed deploys; the `*_signed` methods here do that. Public
//! variants remain for values that do not depend on freshness.

use std::collections::BTreeMap;

use rcash_chain::rho_expr::{Reply, RhoValue};
use rcash_chain::ChainError;
use rcash_core::assets::AssetId;
use rcash_core::Amount;

use crate::{terms, Client};

/// The components key of the launch pool.
pub const POOL_KEY: &str = "pool:NGN/KES:fpmm";
/// The components key of the launch transfer book.
pub const BOOK_KEY: &str = "transfer:NGN/KES";

/// A pool swap quote.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Quote {
    pub amount_out: i64,
    pub fee: i64,
    pub rate: i64,
    pub max_in: i64,
}

/// The quote-side amount matching a base-side deposit.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct QuoteAdd {
    pub base: i64,
    pub quote: i64,
}

/// Pool reserves and health.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Reserves {
    pub base: i64,
    pub quote: i64,
    pub total_shares: i64,
    pub rate: i64,
    pub fresh: bool,
    pub paused: bool,
}

/// One currency's oracle feed.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PriceFeed {
    pub price: i64,
    pub height: i64,
    pub fresh: bool,
    pub reason: String,
}

/// A cross rate derived from two feeds.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FxRate {
    pub rate: i64,
    pub fresh: bool,
    pub reason: String,
}

/// A transfer's public record.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TransferInfo {
    pub sender: String,
    pub source: String,
    pub dest: String,
    pub amount: i64,
    pub claim_hash_hex: String,
    pub expiry: i64,
    pub status: String,
}

/// An account's balances by asset.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Balances {
    pub owner_id: String,
    pub amounts: BTreeMap<String, Amount>,
}

impl Client {
    // --- oracle -------------------------------------------------------------

    /// `OracleHub.get(currency)`.
    pub async fn oracle_price(&self, currency: &str) -> Result<PriceFeed, ChainError> {
        let uri = self.require_manifest()?.oracle_uri.clone();
        let call = terms::args(&["\"get\"".to_string(), terms::s(currency)?]);
        let values = self
            .explore_reply(&terms::uri_call(&uri, &call))
            .await?
            .into_result()?;
        let map = values
            .first()
            .and_then(RhoValue::as_map)
            .ok_or_else(|| decode("oracle get did not return a map"))?;
        Ok(PriceFeed {
            price: map_int(map, "price")?,
            height: map_int(map, "height")?,
            fresh: map_bool(map, "fresh")?,
            reason: map_str(map, "reason")?,
        })
    }

    /// `OracleHub.getPair(base, quote)`.
    pub async fn oracle_pair(&self, base: &str, quote: &str) -> Result<FxRate, ChainError> {
        let uri = self.require_manifest()?.oracle_uri.clone();
        let call = terms::args(&["\"getPair\"".to_string(), terms::s(base)?, terms::s(quote)?]);
        let values = self
            .explore_reply(&terms::uri_call(&uri, &call))
            .await?
            .into_result()?;
        let map = values
            .first()
            .and_then(RhoValue::as_map)
            .ok_or_else(|| decode("oracle getPair did not return a map"))?;
        Ok(FxRate {
            rate: map_int(map, "rate")?,
            fresh: map_bool(map, "fresh")?,
            reason: map_str(map, "reason")?,
        })
    }

    /// `OracleHub.reporters()` as hex public keys.
    pub async fn oracle_reporters(&self) -> Result<Vec<String>, ChainError> {
        let uri = self.require_manifest()?.oracle_uri.clone();
        let values = self
            .explore_reply(&terms::uri_call(&uri, "\"reporters\""))
            .await?
            .into_result()?;
        let list = values
            .first()
            .and_then(RhoValue::as_list)
            .ok_or_else(|| decode("reporters did not return a list"))?;
        list.iter()
            .map(|value| match value {
                RhoValue::Bytes(hex) => Ok(hex.clone()),
                other => Err(decode(format!("reporter is not bytes: {other:?}"))),
            })
            .collect()
    }

    // --- pool ---------------------------------------------------------------

    /// `pool.quote(assetIn, amountIn)`.
    pub async fn pool_quote(&self, asset_in: &str, amount_in: i64) -> Result<Quote, ChainError> {
        AssetId::new(asset_in)?;
        let components = self.require_manifest()?.components_uri.clone();
        let call = terms::args(&[
            "\"quote\"".to_string(),
            terms::s(asset_in)?,
            terms::n(amount_in),
        ]);
        let values = self
            .explore_reply(&terms::component_call(&components, POOL_KEY, &call)?)
            .await?
            .into_result()?;
        Ok(Quote {
            amount_out: int_at(&values, 0)?,
            fee: int_at(&values, 1)?,
            rate: int_at(&values, 2)?,
            max_in: int_at(&values, 3)?,
        })
    }

    /// `pool.quoteAdd(baseAmount)`.
    pub async fn pool_quote_add(&self, base_amount: i64) -> Result<QuoteAdd, ChainError> {
        let components = self.require_manifest()?.components_uri.clone();
        let call = terms::args(&["\"quoteAdd\"".to_string(), terms::n(base_amount)]);
        let values = self
            .explore_reply(&terms::component_call(&components, POOL_KEY, &call)?)
            .await?
            .into_result()?;
        Ok(QuoteAdd {
            base: int_at(&values, 0)?,
            quote: int_at(&values, 1)?,
        })
    }

    /// `pool.reserves()`.
    pub async fn pool_reserves(&self) -> Result<Reserves, ChainError> {
        let components = self.require_manifest()?.components_uri.clone();
        let values = self
            .explore_reply(&terms::component_call(
                &components,
                POOL_KEY,
                "\"reserves\"",
            )?)
            .await?
            .into_result()?;
        Ok(Reserves {
            base: int_at(&values, 0)?,
            quote: int_at(&values, 1)?,
            total_shares: int_at(&values, 2)?,
            rate: int_at(&values, 3)?,
            fresh: bool_at(&values, 4)?,
            paused: bool_at(&values, 5)?,
        })
    }

    /// `pool.params()` as the raw map.
    pub async fn pool_params(&self) -> Result<BTreeMap<String, RhoValue>, ChainError> {
        let components = self.require_manifest()?.components_uri.clone();
        let values = self
            .explore_reply(&terms::component_call(&components, POOL_KEY, "\"params\"")?)
            .await?
            .into_result()?;
        Ok(values
            .first()
            .and_then(RhoValue::as_map)
            .ok_or_else(|| decode("pool params did not return a map"))?
            .clone())
    }

    /// `pool.pair()` as `(base, quote)`.
    pub async fn pool_pair(&self) -> Result<(String, String), ChainError> {
        let components = self.require_manifest()?.components_uri.clone();
        let values = self
            .explore_reply(&terms::component_call(&components, POOL_KEY, "\"pair\"")?)
            .await?
            .into_result()?;
        Ok((str_at(&values, 0)?, str_at(&values, 1)?))
    }

    /// `pool.lpAsset()` as the raw brand/issuer values.
    pub async fn pool_lp_asset(&self) -> Result<Vec<RhoValue>, ChainError> {
        let components = self.require_manifest()?.components_uri.clone();
        self.explore_reply(&terms::component_call(
            &components,
            POOL_KEY,
            "\"lpAsset\"",
        )?)
        .await?
        .into_result()
    }

    // --- transfer book ------------------------------------------------------

    /// `book.info(transferId)`.
    pub async fn transfer_info(&self, transfer_id: i64) -> Result<TransferInfo, ChainError> {
        let components = self.require_manifest()?.components_uri.clone();
        let call = terms::args(&["\"info\"".to_string(), terms::n(transfer_id)]);
        let values = self
            .explore_reply(&terms::component_call(&components, BOOK_KEY, &call)?)
            .await?
            .into_result()?;
        let map = values
            .first()
            .and_then(RhoValue::as_map)
            .ok_or_else(|| decode("transfer info did not return a map"))?;
        Ok(TransferInfo {
            sender: map_str(map, "sender")?,
            source: map_str(map, "source")?,
            dest: map_str(map, "dest")?,
            amount: map_int(map, "amount")?,
            claim_hash_hex: map_hex(map, "claimHash")?,
            expiry: map_int(map, "expiry")?,
            status: map_str(map, "status")?,
        })
    }

    /// Deprecated: transfers carry a per-owner id; the book has no shared counter.
    ///
    /// Kept so existing callers compile. It returns 0 instead of reading a cell that no
    /// longer exists.
    pub async fn transfer_next_id(&self) -> Result<i64, ChainError> {
        Ok(0)
    }

    /// `book.quote(source, dest, amount)`.
    pub async fn transfer_quote(
        &self,
        source: &str,
        dest: &str,
        amount: i64,
    ) -> Result<Quote, ChainError> {
        AssetId::new(source)?;
        AssetId::new(dest)?;
        let components = self.require_manifest()?.components_uri.clone();
        let call = terms::args(&[
            "\"quote\"".to_string(),
            terms::s(source)?,
            terms::s(dest)?,
            terms::n(amount),
        ]);
        let values = self
            .explore_reply(&terms::component_call(&components, BOOK_KEY, &call)?)
            .await?
            .into_result()?;
        Ok(Quote {
            amount_out: int_at(&values, 0)?,
            fee: int_at(&values, 1)?,
            rate: int_at(&values, 2)?,
            max_in: int_at(&values, 3)?,
        })
    }

    // --- native REV and the account ----------------------------------------

    /// The native REV balance of an address, in drops. Zero when the address has no vault.
    pub async fn native_rev_balance(&self, address: &str) -> Result<i64, ChainError> {
        let term = terms::rev_balance(address)?;
        match self.explore_value(&term).await? {
            Some(value) => value
                .as_int()
                .ok_or_else(|| decode("REV balance is not an integer")),
            None => Ok(0),
        }
    }

    // --- signed reads for freshness-gated arms ------------------------------
    //
    // `explore-deploy` runs with no block context: `rho:block:data` reports height 0, so
    // every arm that checks staleness answers "stale" there. These variants run the same
    // arm in a signed deploy, where the height is real. They cost phlo.

    /// `OracleHub.get(currency)` as a signed read (accurate `fresh`).
    pub async fn oracle_price_signed(&self, currency: &str) -> Result<PriceFeed, ChainError> {
        let uri = self.require_manifest()?.oracle_uri.clone();
        let call = terms::args(&["\"get\"".to_string(), terms::s(currency)?]);
        let value = self
            .signed_value(&terms::uri_call_deploy(&uri, &call))
            .await?;
        let values = Reply::from_value(&value)?.into_result()?;
        let map = values
            .first()
            .and_then(RhoValue::as_map)
            .ok_or_else(|| decode("oracle get did not return a map"))?;
        Ok(PriceFeed {
            price: map_int(map, "price")?,
            height: map_int(map, "height")?,
            fresh: map_bool(map, "fresh")?,
            reason: map_str(map, "reason")?,
        })
    }

    /// `OracleHub.getPair(base, quote)` as a signed read.
    pub async fn oracle_pair_signed(&self, base: &str, quote: &str) -> Result<FxRate, ChainError> {
        let uri = self.require_manifest()?.oracle_uri.clone();
        let call = terms::args(&["\"getPair\"".to_string(), terms::s(base)?, terms::s(quote)?]);
        let value = self
            .signed_value(&terms::uri_call_deploy(&uri, &call))
            .await?;
        let values = Reply::from_value(&value)?.into_result()?;
        let map = values
            .first()
            .and_then(RhoValue::as_map)
            .ok_or_else(|| decode("oracle getPair did not return a map"))?;
        Ok(FxRate {
            rate: map_int(map, "rate")?,
            fresh: map_bool(map, "fresh")?,
            reason: map_str(map, "reason")?,
        })
    }

    /// `pool.quote(assetIn, amountIn)` as a signed read.
    pub async fn pool_quote_signed(
        &self,
        asset_in: &str,
        amount_in: i64,
    ) -> Result<Quote, ChainError> {
        AssetId::new(asset_in)?;
        let components = self.require_manifest()?.components_uri.clone();
        let call = terms::args(&[
            "\"quote\"".to_string(),
            terms::s(asset_in)?,
            terms::n(amount_in),
        ]);
        let value = self
            .signed_value(&terms::component_call_deploy(&components, POOL_KEY, &call)?)
            .await?;
        let values = Reply::from_value(&value)?.into_result()?;
        Ok(Quote {
            amount_out: int_at(&values, 0)?,
            fee: int_at(&values, 1)?,
            rate: int_at(&values, 2)?,
            max_in: int_at(&values, 3)?,
        })
    }

    /// `pool.quoteAdd(baseAmount)` as a signed read.
    pub async fn pool_quote_add_signed(&self, base_amount: i64) -> Result<QuoteAdd, ChainError> {
        let components = self.require_manifest()?.components_uri.clone();
        let call = terms::args(&["\"quoteAdd\"".to_string(), terms::n(base_amount)]);
        let value = self
            .signed_value(&terms::component_call_deploy(&components, POOL_KEY, &call)?)
            .await?;
        let values = Reply::from_value(&value)?.into_result()?;
        Ok(QuoteAdd {
            base: int_at(&values, 0)?,
            quote: int_at(&values, 1)?,
        })
    }

    /// `pool.reserves()` as a signed read (accurate rate and freshness).
    pub async fn pool_reserves_signed(&self) -> Result<Reserves, ChainError> {
        let components = self.require_manifest()?.components_uri.clone();
        let term = terms::component_call_deploy(&components, POOL_KEY, "\"reserves\"")?;
        let value = self.signed_value(&term).await?;
        let values = Reply::from_value(&value)?.into_result()?;
        Ok(Reserves {
            base: int_at(&values, 0)?,
            quote: int_at(&values, 1)?,
            total_shares: int_at(&values, 2)?,
            rate: int_at(&values, 3)?,
            fresh: bool_at(&values, 4)?,
            paused: bool_at(&values, 5)?,
        })
    }

    /// `book.quote(source, dest, amount)` as a signed read.
    pub async fn transfer_quote_signed(
        &self,
        source: &str,
        dest: &str,
        amount: i64,
    ) -> Result<Quote, ChainError> {
        AssetId::new(source)?;
        AssetId::new(dest)?;
        let components = self.require_manifest()?.components_uri.clone();
        let call = terms::args(&[
            "\"quote\"".to_string(),
            terms::s(source)?,
            terms::s(dest)?,
            terms::n(amount),
        ]);
        let value = self
            .signed_value(&terms::component_call_deploy(&components, BOOK_KEY, &call)?)
            .await?;
        let values = Reply::from_value(&value)?.into_result()?;
        Ok(Quote {
            amount_out: int_at(&values, 0)?,
            fee: int_at(&values, 1)?,
            rate: int_at(&values, 2)?,
            max_in: int_at(&values, 3)?,
        })
    }

    /// Read several Account balances in one signed deploy.
    pub async fn balances(&self, assets: &[&str]) -> Result<Balances, ChainError> {
        for asset in assets {
            AssetId::new(*asset)?;
        }
        let owned: Vec<String> = assets.iter().map(|a| a.to_string()).collect();
        let factory = self.require_manifest()?.account_factory_uri.clone();
        let value = self
            .signed_value(&terms::balances(&factory, &owned)?)
            .await?;
        let items = value
            .as_tuple()
            .ok_or_else(|| decode("balances reply is not a tuple"))?;
        let owner_id = items
            .first()
            .and_then(RhoValue::as_str)
            .ok_or_else(|| decode("balances reply has no owner id"))?
            .to_string();
        let replies = items
            .get(1)
            .and_then(RhoValue::as_list)
            .ok_or_else(|| decode("balances reply has no list"))?;
        if replies.len() != assets.len() {
            return Err(decode(format!(
                "asked for {} balances, got {}",
                assets.len(),
                replies.len()
            )));
        }
        let mut amounts = BTreeMap::new();
        for (asset, reply) in assets.iter().zip(replies) {
            match Reply::from_value(reply)? {
                Reply::Ok(values) => {
                    let amount = values
                        .first()
                        .and_then(RhoValue::as_int)
                        .ok_or_else(|| decode("balance is not an integer"))?;
                    amounts.insert((*asset).to_string(), Amount::raw(amount));
                }
                // A purse is created on first deposit, so an Account that has never held
                // this asset reports `no purse`. That is a zero balance, not a failure.
                Reply::Refused(reason) if reason == "no purse" => {
                    amounts.insert((*asset).to_string(), Amount::raw(0));
                }
                Reply::Refused(reason) => {
                    return Err(ChainError::Refused(format!("{asset}: {reason}")))
                }
            }
        }
        Ok(Balances { owner_id, amounts })
    }
}

fn decode(message: impl Into<String>) -> ChainError {
    ChainError::Decode(message.into())
}

fn int_at(values: &[RhoValue], index: usize) -> Result<i64, ChainError> {
    values
        .get(index)
        .and_then(RhoValue::as_int)
        .ok_or_else(|| decode(format!("value {index} is not an integer")))
}

fn bool_at(values: &[RhoValue], index: usize) -> Result<bool, ChainError> {
    values
        .get(index)
        .and_then(RhoValue::as_bool)
        .ok_or_else(|| decode(format!("value {index} is not a boolean")))
}

fn str_at(values: &[RhoValue], index: usize) -> Result<String, ChainError> {
    values
        .get(index)
        .and_then(RhoValue::as_str)
        .map(str::to_string)
        .ok_or_else(|| decode(format!("value {index} is not a string")))
}

fn map_int(map: &BTreeMap<String, RhoValue>, key: &str) -> Result<i64, ChainError> {
    map.get(key)
        .and_then(RhoValue::as_int)
        .ok_or_else(|| decode(format!("map key {key} is not an integer")))
}

fn map_bool(map: &BTreeMap<String, RhoValue>, key: &str) -> Result<bool, ChainError> {
    map.get(key)
        .and_then(RhoValue::as_bool)
        .ok_or_else(|| decode(format!("map key {key} is not a boolean")))
}

fn map_str(map: &BTreeMap<String, RhoValue>, key: &str) -> Result<String, ChainError> {
    map.get(key)
        .and_then(RhoValue::as_str)
        .map(str::to_string)
        .ok_or_else(|| decode(format!("map key {key} is not a string")))
}

fn map_hex(map: &BTreeMap<String, RhoValue>, key: &str) -> Result<String, ChainError> {
    match map.get(key) {
        Some(RhoValue::Bytes(hex)) => Ok(hex.clone()),
        Some(RhoValue::Str(value)) => Ok(value.clone()),
        _ => Err(decode(format!("map key {key} is not bytes"))),
    }
}
