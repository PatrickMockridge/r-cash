//! Market terms, feed policy and the canonical strings that are hashed on-chain.
//!
//! Every economic field of a listed market is immutable. Rholang, Rust and Python must
//! produce byte-identical canonical strings; `tests/terms/terms-vectors.json` pins them.

use serde::{Deserialize, Serialize};

use crate::assets::{Currency, RegistryUri};
use crate::CoreError;

/// The terms schema string.
pub const TERMS_SCHEMA: &str = "rcash:market-terms:v4";

/// The one canonical encoding shared with Rholang's `Codec` and Python:
/// `schema|len(v):v|…`, where `len` is the UTF-8 byte length.
pub fn encode(schema: &str, values: &[String]) -> String {
    let encoded: Vec<String> = values
        .iter()
        .map(|v| format!("{}:{}", v.len(), v))
        .collect();
    format!("{schema}|{}", encoded.join("|"))
}
/// The zone-params schema string.
/// The oracle-policy schema string.
pub const FEED_SCHEMA: &str = "rcash:oracle-policy:v3";
/// The pool-params schema string.
pub const POOL_SCHEMA: &str = "rcash:pool-params:v1";
/// The book-params schema string.
pub const BOOK_SCHEMA: &str = "rcash:book-params:v4";
/// Sponsor consent for a market.
pub const SPONSOR_SCHEMA: &str = "rcash:market-create:v1";
/// Sponsor consent for a currency.
pub const CURRENCY_SPONSOR_SCHEMA: &str = "rcash:listing-currency:v1";

/// Market lifecycle.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MarketStatus {
    Draft,
    Active,
    Paused,
    Delisted,
    Cancelled,
}

impl MarketStatus {
    pub fn is_active(self) -> bool {
        matches!(self, Self::Active)
    }
}

/// A per-currency oracle feed policy.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct FeedPolicy {
    pub quorum: i64,
    pub max_age_blocks: i64,
    pub max_spread_bps: i64,
    pub min_price: i64,
    pub max_price: i64,
    pub trial_blocks: i64,
    pub trial_min_submits: i64,
}

impl FeedPolicy {
    pub fn values(&self) -> Vec<String> {
        vec![
            self.quorum.to_string(),
            self.max_age_blocks.to_string(),
            self.max_spread_bps.to_string(),
            self.min_price.to_string(),
            self.max_price.to_string(),
            self.trial_blocks.to_string(),
            self.trial_min_submits.to_string(),
        ]
    }

    pub fn canonical(&self) -> String {
        encode(FEED_SCHEMA, &self.values())
    }

    pub fn violations(&self) -> Vec<String> {
        let mut out = Vec::new();
        if self.quorum != 2 {
            out.push("quorum must be exactly 2".into());
        }
        if !(5..=1_000).contains(&self.max_age_blocks) {
            out.push("maxAgeBlocks must be 5..1000".into());
        }
        if !(50..=1_000).contains(&self.max_spread_bps) {
            out.push("maxSpreadBps must be 50..1000".into());
        }
        if self.min_price < 1 || self.max_price > 1_000_000_000_000 {
            out.push("price band must lie inside [1, 1e12]".into());
        }
        if !(10..=43_200).contains(&self.trial_blocks) {
            out.push("trialBlocks must be 10..43200".into());
        }
        if !(4..=10_000).contains(&self.trial_min_submits) {
            out.push("trialMinSubmits must be 4..10000".into());
        }
        out
    }
}

/// Pool parameters fixed at listing.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct PoolParams {
    pub base_spread_bps: i64,
    pub skew_spread_bps: i64,
    pub max_trade_bps: i64,
    pub min_liquidity: i64,
    pub first_deposit_tolerance_bps: i64,
    pub depth_floor_quote: i64,
    pub min_ticket_quote: i64,
}

impl PoolParams {
    pub fn values(&self) -> Vec<String> {
        vec![
            self.base_spread_bps.to_string(),
            self.skew_spread_bps.to_string(),
            self.max_trade_bps.to_string(),
            self.min_liquidity.to_string(),
            self.first_deposit_tolerance_bps.to_string(),
            self.depth_floor_quote.to_string(),
            self.min_ticket_quote.to_string(),
        ]
    }

    pub fn canonical(&self) -> String {
        encode(POOL_SCHEMA, &self.values())
    }

    pub fn violations(&self) -> Vec<String> {
        let mut out = Vec::new();
        if !(1..=100).contains(&self.base_spread_bps) {
            out.push("baseSpreadBps must be 1..100".into());
        }
        if !(0..=200).contains(&self.skew_spread_bps) {
            out.push("skewSpreadBps must be 0..200".into());
        }
        if !(100..=2_000).contains(&self.max_trade_bps) {
            out.push("maxTradeBps must be 100..2000".into());
        }
        if self.min_liquidity != 100_000_000 {
            out.push("minLiquidity must be exactly 1e8".into());
        }
        if !(10..=500).contains(&self.first_deposit_tolerance_bps) {
            out.push("firstDepositToleranceBps must be 10..500".into());
        }
        if self.depth_floor_quote < 1 || self.min_ticket_quote < 1 {
            out.push("depth floor and min ticket must be positive quote units".into());
        }
        out
    }
}

/// Transfer-book parameters fixed at listing.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct BookParams {
    pub default_expiry_blocks: i64,
    pub max_expiry_blocks: i64,
    pub min_amount: i64,
    pub max_memo_bytes: i64,
    pub max_op_id_bytes: i64,
    pub max_stipend: i64,
}

impl BookParams {
    pub fn values(&self) -> Vec<String> {
        vec![
            self.default_expiry_blocks.to_string(),
            self.max_expiry_blocks.to_string(),
            self.min_amount.to_string(),
            self.max_memo_bytes.to_string(),
            self.max_op_id_bytes.to_string(),
            self.max_stipend.to_string(),
        ]
    }

    pub fn canonical(&self) -> String {
        encode(BOOK_SCHEMA, &self.values())
    }

    pub fn violations(&self) -> Vec<String> {
        let mut out = Vec::new();
        if !(1..=1_296_000).contains(&self.default_expiry_blocks) {
            out.push("defaultExpiryBlocks must be 1..1296000".into());
        }
        if self.max_expiry_blocks < self.default_expiry_blocks || self.max_expiry_blocks > 1_296_000
        {
            out.push("maxExpiryBlocks must be >= default and <= 1296000".into());
        }
        if self.min_amount < 0 {
            out.push("minAmount must be non-negative".into());
        }
        if !(0..=4_096).contains(&self.max_memo_bytes) {
            out.push("maxMemoBytes must be 0..4096".into());
        }
        if !(0..=256).contains(&self.max_op_id_bytes) {
            out.push("maxOpIdBytes must be 0..256".into());
        }
        if self.max_stipend < 0 {
            out.push("maxStipend must be non-negative".into());
        }
        out
    }
}

/// The immutable terms of one listed market.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarketTerms {
    pub market_id: String,
    pub slug: String,
    pub base: Currency,
    pub quote: Currency,
    pub version: i64,
    pub sponsor_pub_key: String,
    pub sponsor_owner_id: String,
    pub base_feed_policy_hash: String,
    pub quote_feed_policy_hash: String,
    pub base_spread_bps: i64,
    pub skew_spread_bps: i64,
    pub max_trade_bps: i64,
    pub min_liquidity: i64,
    pub first_deposit_tolerance_bps: i64,
    pub depth_floor_quote: i64,
    pub min_ticket_quote: i64,
    pub seed_base: i64,
    pub seed_quote: i64,
    pub seed_initial_shares: i64,
    pub lock_beneficiary_pub_key: String,
    pub lock_min_blocks: i64,
    pub lock_until_height: i64,
    pub book_default_expiry_blocks: i64,
    pub book_max_expiry_blocks: i64,
    pub max_pair_age_blocks: i64,
}

impl MarketTerms {
    /// The canonical values in schema order. This order is normative; append-only.
    pub fn values(&self) -> Vec<String> {
        vec![
            self.market_id.clone(),
            self.slug.clone(),
            self.base.to_string(),
            self.quote.to_string(),
            self.version.to_string(),
            self.sponsor_pub_key.clone(),
            self.sponsor_owner_id.clone(),
            self.base_feed_policy_hash.clone(),
            self.quote_feed_policy_hash.clone(),
            self.base_spread_bps.to_string(),
            self.skew_spread_bps.to_string(),
            self.max_trade_bps.to_string(),
            self.min_liquidity.to_string(),
            self.first_deposit_tolerance_bps.to_string(),
            self.depth_floor_quote.to_string(),
            self.min_ticket_quote.to_string(),
            self.seed_base.to_string(),
            self.seed_quote.to_string(),
            self.seed_initial_shares.to_string(),
            self.lock_beneficiary_pub_key.clone(),
            self.lock_min_blocks.to_string(),
            self.lock_until_height.to_string(),
            self.book_default_expiry_blocks.to_string(),
            self.book_max_expiry_blocks.to_string(),
            self.max_pair_age_blocks.to_string(),
        ]
    }

    pub fn canonical(&self) -> String {
        encode(TERMS_SCHEMA, &self.values())
    }

    /// Validate the immutable terms against the protocol bounds.
    pub fn violations(&self) -> Vec<String> {
        let mut out = Vec::new();
        if self.market_id.is_empty() || self.slug.is_empty() {
            out.push("market id and slug are required".into());
        }
        if self.version < 1 {
            out.push("version must be >= 1".into());
        }
        if self.base == self.quote {
            out.push("base and quote must differ".into());
        }
        if self.base_spread_bps < 1 || self.base_spread_bps > 100 {
            out.push("baseSpreadBps must be 1..100".into());
        }
        if self.skew_spread_bps < 0 || self.skew_spread_bps > 200 {
            out.push("skewSpreadBps must be 0..200".into());
        }
        if self.max_trade_bps < 100 || self.max_trade_bps > 2_000 {
            out.push("maxTradeBps must be 100..2000".into());
        }
        if self.min_liquidity < 1 {
            out.push("minLiquidity must be positive".into());
        }
        if self.first_deposit_tolerance_bps < 0 || self.first_deposit_tolerance_bps > 1_000 {
            out.push("firstDepositToleranceBps must be 0..1000".into());
        }
        if self.depth_floor_quote < 1 || self.min_ticket_quote < 1 {
            out.push("depth floor and min ticket must be positive quote units".into());
        }
        if self.seed_base < 1 || self.seed_quote < 1 || self.seed_initial_shares < 1 {
            out.push("seed amounts and initial shares must be positive".into());
        }
        if self.lock_beneficiary_pub_key != self.sponsor_pub_key {
            out.push("lock beneficiary must be the sponsor".into());
        }
        if self.lock_min_blocks < 1 {
            out.push("lockMinBlocks must be positive".into());
        }
        if self.lock_until_height < self.lock_min_blocks {
            out.push("lockUntilHeight is below the minimum lock".into());
        }
        if self.book_default_expiry_blocks < 1
            || self.book_max_expiry_blocks < self.book_default_expiry_blocks
            || self.book_max_expiry_blocks > 1_296_000
        {
            out.push("book expiry bounds are invalid".into());
        }
        if !(1..=1_000).contains(&self.max_pair_age_blocks) {
            out.push("maxPairAgeBlocks must be 1..1000".into());
        }
        out
    }

    /// The sponsor consent payload for this market and terms hash.
    pub fn sponsor_payload(&self, terms_hash: &str) -> String {
        format!(
            "{SPONSOR_SCHEMA}|{}|{}|{}",
            self.market_id, terms_hash, self.sponsor_pub_key
        )
    }

    /// Convert a USD×1e8 amount to quote base units at `price_quote`.
    pub fn quote_units_for_usd(usd_e8: i64, price_quote: i64) -> Result<i64, CoreError> {
        if price_quote <= 0 {
            return Err(CoreError::BadManifest(
                "quote price must be positive".into(),
            ));
        }
        let value = (usd_e8 as i128 * 100_000_000i128) / price_quote as i128;
        i64::try_from(value).map_err(|_| CoreError::AmountOutOfRange("USD conversion".into()))
    }
}

/// A market view safe to serialize (no capabilities).
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarketView {
    pub market_id: String,
    pub slug: String,
    pub base: Currency,
    pub quote: Currency,
    pub status: MarketStatus,
    pub sponsor_owner_id: String,
    pub lp_asset: String,
    pub terms_hash: String,
    pub lock_until_height: i64,
    pub depth_floor_quote: i64,
    pub min_ticket_quote: i64,
}

/// A currency view.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct CurrencyView {
    pub code: Currency,
    pub zone_uri: RegistryUri,
    pub params_hash: String,
    pub status: MarketStatus,
    pub sponsor_owner_id: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn terms() -> MarketTerms {
        MarketTerms {
            market_id: "KES/NGN:v1".into(),
            slug: "KES-NGN-v1".into(),
            base: Currency::new("NGN").unwrap(),
            quote: Currency::new("KES").unwrap(),
            version: 1,
            sponsor_pub_key: "04aa".into(),
            sponsor_owner_id: "1111sponsor".into(),
            base_feed_policy_hash: "11".repeat(32),
            quote_feed_policy_hash: "22".repeat(32),
            base_spread_bps: 20,
            skew_spread_bps: 80,
            max_trade_bps: 500,
            min_liquidity: 100_000_000,
            first_deposit_tolerance_bps: 100,
            depth_floor_quote: 130_000_000_000,
            min_ticket_quote: 1_300_000_000,
            seed_base: 1_500_000_000_000,
            seed_quote: 130_000_000_000,
            seed_initial_shares: 2_000_000_000,
            lock_beneficiary_pub_key: "04aa".into(),
            lock_min_blocks: 302_400,
            lock_until_height: 500_000,
            book_default_expiry_blocks: 720,
            book_max_expiry_blocks: 129_600,
            max_pair_age_blocks: 50,
        }
    }

    #[test]
    fn canonical_form_is_stable_and_ordered() {
        let canonical = terms().canonical();
        assert!(canonical.starts_with("rcash:market-terms:v4|"));
        assert!(canonical.contains("|10:KES/NGN:v1|10:KES-NGN-v1|3:NGN|3:KES|1:1|"));
        assert_eq!(terms().values().len(), 25);
        assert_eq!(canonical.split('|').count(), 26);
    }

    #[test]
    fn bounds_catch_bad_terms() {
        let mut bad = terms();
        bad.seed_base = 0;
        bad.base = bad.quote.clone();
        bad.max_trade_bps = 5_000;
        let violations = bad.violations();
        assert!(violations.iter().any(|v| v.contains("seed")));
        assert!(violations.iter().any(|v| v.contains("base and quote")));
        assert!(violations.iter().any(|v| v.contains("maxTradeBps")));
        assert!(terms().violations().is_empty());
    }

    #[test]
    fn sponsor_payload_binds_the_terms_hash() {
        assert_eq!(
            terms().sponsor_payload("abc"),
            "rcash:market-create:v1|KES/NGN:v1|abc|04aa"
        );
    }

    #[test]
    fn sample_matches_the_python_vectors() {
        let vectors: serde_json::Value =
            serde_json::from_str(include_str!("../../../tests/terms/terms-vectors.json"))
                .expect("vectors");
        let feed = FeedPolicy {
            quorum: 2,
            max_age_blocks: 50,
            max_spread_bps: 200,
            min_price: 1,
            max_price: 1_000_000_000_000,
            trial_blocks: 10,
            trial_min_submits: 4,
        };
        assert_eq!(
            feed.canonical(),
            vectors["feed"]["canonical"].as_str().unwrap()
        );
        let pool = PoolParams {
            base_spread_bps: 20,
            skew_spread_bps: 80,
            max_trade_bps: 500,
            min_liquidity: 100_000_000,
            first_deposit_tolerance_bps: 100,
            depth_floor_quote: 130_000_000_000,
            min_ticket_quote: 1_300_000_000,
        };
        assert_eq!(
            pool.canonical(),
            vectors["pool"]["canonical"].as_str().unwrap()
        );
        let book = BookParams {
            default_expiry_blocks: 720,
            max_expiry_blocks: 129_600,
            min_amount: 1,
            max_memo_bytes: 128,
            max_op_id_bytes: 64,
            max_stipend: 100_000_000,
        };
        assert_eq!(
            book.canonical(),
            vectors["book"]["canonical"].as_str().unwrap()
        );
        assert_eq!(
            terms().canonical(),
            vectors["terms"]["canonical"].as_str().unwrap()
        );
    }

    #[test]
    fn usd_conversion_matches_the_spec_examples() {
        // $1 floor and $0.01 ticket with KES at 769,230.
        assert_eq!(
            MarketTerms::quote_units_for_usd(100_000_000, 769_230).unwrap(),
            13_000_013_000
        );
        assert_eq!(
            MarketTerms::quote_units_for_usd(1_000_000, 769_230).unwrap(),
            130_000_130
        );
    }
}
