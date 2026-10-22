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
