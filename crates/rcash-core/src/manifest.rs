//! The deployment manifest (`deployments/devnet.json`).
//!
//! The manifest is public: it names installed components and contains no keys. It is
//! written by the install path and read by every client.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::assets::RegistryUri;
use crate::error::CoreError;

/// Installed R-Cash component URIs and the block they were installed in.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Manifest {
    pub directory_uri: RegistryUri,
    pub account_factory_uri: RegistryUri,
    pub oracle_uri: RegistryUri,
    pub zone_ngn_uri: RegistryUri,
    pub zone_kes_uri: RegistryUri,
    pub components_uri: RegistryUri,
    #[serde(default)]
    pub block_hash: Option<String>,
    #[serde(default)]
    pub block_number: Option<i64>,
    #[serde(default)]
    pub deploy_id: Option<String>,
    #[serde(default)]
    pub node_commit: Option<String>,
    #[serde(default)]
    pub generated: Option<String>,
    #[serde(default)]
    pub pool_installed: bool,
    #[serde(default)]
    pub transfer_installed: bool,
    /// Currency code to zone URI, for corridors beyond the two bootstrap zones.
    #[serde(default)]
    pub zones: BTreeMap<String, RegistryUri>,
}

impl Manifest {
    /// The zone URI for a currency code.
    pub fn zone(&self, currency: &str) -> Option<&RegistryUri> {
        match currency {
            "NGN" => Some(&self.zone_ngn_uri),
            "KES" => Some(&self.zone_kes_uri),
            other => self.zones.get(other),
        }
    }

    /// Parse and validate a manifest document.
    pub fn from_json(text: &str) -> Result<Self, CoreError> {
        let manifest: Manifest =
            serde_json::from_str(text).map_err(|e| CoreError::BadManifest(e.to_string()))?;
        manifest.validate()?;
        Ok(manifest)
    }

    /// Check the invariants a client depends on.
    pub fn validate(&self) -> Result<(), CoreError> {
        if self.directory_uri.as_str().is_empty() {
            return Err(CoreError::BadManifest("directory_uri is empty".into()));
        }
        if !self.pool_installed && !self.transfer_installed {
            // Not an error: a fresh bootstrap manifest is valid. Kept as a place for
            // future cross-checks rather than inventing one now.
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"{
        "directory_uri": "rho:id:abc",
        "account_factory_uri": "rho:id:def",
        "oracle_uri": "rho:id:ghi",
        "zone_ngn_uri": "rho:id:jkl",
        "zone_kes_uri": "rho:id:mno",
        "components_uri": "rho:id:pqr",
        "pool_installed": true
    }"#;

    #[test]
    fn parses_the_devnet_shape() {
        let manifest = Manifest::from_json(SAMPLE).unwrap();
        assert_eq!(manifest.zone("NGN").unwrap().as_str(), "rho:id:jkl");
        assert_eq!(manifest.zone("KES").unwrap().as_str(), "rho:id:mno");
        assert!(manifest.zone("GHS").is_none());
        assert!(manifest.pool_installed);
        assert!(!manifest.transfer_installed);
    }
}

/// The v0.4 deployment manifest (`deployments/devnet-v4.json`).
///
/// It names the installed component URIs; currencies and markets are discovered
/// through `ListingViews`, not copied here.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct V4Manifest {
    pub root_uri: RegistryUri,
    pub clock_uri: RegistryUri,
    pub verifier_uri: RegistryUri,
    pub codec_uri: RegistryUri,
    pub bounds_uri: RegistryUri,
    pub admin_guard_uri: RegistryUri,
    pub governor_uri: RegistryUri,
    pub amm_math_uri: RegistryUri,
    pub oracle_registry_uri: RegistryUri,
    pub oracle_hub_uri: RegistryUri,
    pub currency_registry_uri: RegistryUri,
    pub stablecoin_directory_uri: RegistryUri,
    pub asset_resolver_uri: RegistryUri,
    pub transfer_book_uri: RegistryUri,
    pub pool_template_uri: RegistryUri,
    pub market_terms_uri: RegistryUri,
    pub market_directory_uri: RegistryUri,
    pub market_index_uri: RegistryUri,
    pub market_factory_uri: RegistryUri,
    pub tradability_gate_uri: RegistryUri,
    pub listing_views_uri: RegistryUri,
    pub account_factory_uri: RegistryUri,
    #[serde(default)]
    pub block_number: Option<i64>,
    #[serde(default)]
    pub block_hash: Option<String>,
    #[serde(default)]
    pub generated: Option<String>,
}

impl V4Manifest {
    /// Parse and validate a v0.4 manifest document.
    pub fn from_json(text: &str) -> Result<Self, CoreError> {
        let manifest: V4Manifest =
            serde_json::from_str(text).map_err(|e| CoreError::BadManifest(e.to_string()))?;
        manifest.validate()?;
        Ok(manifest)
    }

    /// Every named component must be a registry URI.
    pub fn validate(&self) -> Result<(), CoreError> {
        for (name, uri) in self.uris() {
            if !uri.as_str().starts_with("rho:id:") {
                return Err(CoreError::BadManifest(format!(
                    "{name} is not a registry URI: {}",
                    uri.as_str()
                )));
            }
        }
        Ok(())
    }

    /// Named component URIs, for validation and manifests.
    pub fn uris(&self) -> Vec<(&'static str, &RegistryUri)> {
        vec![
            ("root_uri", &self.root_uri),
            ("clock_uri", &self.clock_uri),
            ("verifier_uri", &self.verifier_uri),
            ("codec_uri", &self.codec_uri),
            ("bounds_uri", &self.bounds_uri),
            ("admin_guard_uri", &self.admin_guard_uri),
            ("governor_uri", &self.governor_uri),
            ("amm_math_uri", &self.amm_math_uri),
            ("oracle_registry_uri", &self.oracle_registry_uri),
            ("oracle_hub_uri", &self.oracle_hub_uri),
            ("currency_registry_uri", &self.currency_registry_uri),
            ("stablecoin_directory_uri", &self.stablecoin_directory_uri),
            ("asset_resolver_uri", &self.asset_resolver_uri),
            ("transfer_book_uri", &self.transfer_book_uri),
            ("pool_template_uri", &self.pool_template_uri),
            ("market_terms_uri", &self.market_terms_uri),
            ("market_directory_uri", &self.market_directory_uri),
            ("market_index_uri", &self.market_index_uri),
            ("market_factory_uri", &self.market_factory_uri),
            ("tradability_gate_uri", &self.tradability_gate_uri),
            ("listing_views_uri", &self.listing_views_uri),
            ("account_factory_uri", &self.account_factory_uri),
        ]
    }
}

#[cfg(test)]
mod v4_tests {
    use super::*;

    const SAMPLE: &str = r#"{
        "root_uri": "rho:id:root",
        "clock_uri": "rho:id:clock",
        "verifier_uri": "rho:id:verifier",
        "codec_uri": "rho:id:codec",
        "bounds_uri": "rho:id:bounds",
        "admin_guard_uri": "rho:id:guard",
        "governor_uri": "rho:id:governor",
        "amm_math_uri": "rho:id:amm",
        "oracle_registry_uri": "rho:id:oreg",
        "oracle_hub_uri": "rho:id:ohub",
        "currency_registry_uri": "rho:id:creg",
        "stablecoin_directory_uri": "rho:id:sdir",
        "asset_resolver_uri": "rho:id:assets",
        "transfer_book_uri": "rho:id:book",
        "pool_template_uri": "rho:id:pool",
        "market_terms_uri": "rho:id:terms",
        "market_directory_uri": "rho:id:mdir",
        "market_index_uri": "rho:id:mindex",
        "market_factory_uri": "rho:id:mfactory",
        "tradability_gate_uri": "rho:id:gate",
        "listing_views_uri": "rho:id:views",
        "account_factory_uri": "rho:id:accounts"
    }"#;

    #[test]
    fn parses_the_v4_shape() {
        let manifest = V4Manifest::from_json(SAMPLE).unwrap();
        assert_eq!(manifest.account_factory_uri.as_str(), "rho:id:accounts");
        assert_eq!(manifest.uris().len(), 22);
    }

    #[test]
    fn rejects_a_non_registry_uri() {
        let bad = SAMPLE.replace("rho:id:accounts", "not-a-uri");
        assert!(V4Manifest::from_json(&bad).is_err());
    }
}
