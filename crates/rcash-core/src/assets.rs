//! Validated identifiers used to build Rholang terms.
//!
//! Rholang string literals have no escape processing, so a user-supplied string that
//! contains `"` cannot be represented at all. Rather than trying to escape, every value
//! that reaches a term is a newtype with a closed character set.

use serde::{Deserialize, Serialize};

use crate::error::CoreError;

/// An asset identifier: `REV`, `NGN`, `LP:NGN/KES:fpmm`, ...
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct AssetId(String);

impl AssetId {
    /// Validate and wrap an asset id.
    pub fn new(value: impl Into<String>) -> Result<Self, CoreError> {
        let value = value.into();
        let valid = !value.is_empty()
            && value.len() <= 96
            && value
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, ':' | '/' | '-' | '_'));
        if valid {
            Ok(Self(value))
        } else {
            Err(CoreError::BadAssetId(value))
        }
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl std::fmt::Display for AssetId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

/// A local currency code: `NGN`, `KES`, `GHS`, ...
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Currency(String);

impl Currency {
    /// Validate and wrap a currency code (2-8 ASCII alphanumerics, upper-case by convention).
    pub fn new(value: impl Into<String>) -> Result<Self, CoreError> {
        let value = value.into();
        let valid =
            (2..=8).contains(&value.len()) && value.chars().all(|c| c.is_ascii_alphanumeric());
        if valid {
            Ok(Self(value))
        } else {
            Err(CoreError::BadCurrency(value))
        }
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl std::fmt::Display for Currency {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

/// A `rho:id:` registry URI, as emitted by `rho:registry:insert*`.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct RegistryUri(String);

impl RegistryUri {
    /// Validate and wrap a registry URI. Rholang URIs are backtick literals, so a
    /// backtick in the payload is unrepresentable.
    pub fn new(value: impl Into<String>) -> Result<Self, CoreError> {
        let value = value.into();
        let payload = value
            .strip_prefix("rho:id:")
            .ok_or_else(|| CoreError::BadUri(value.clone()))?;
        let valid = !payload.is_empty()
            && payload
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, ':' | '/' | '-' | '_'));
        if valid {
            Ok(Self(value))
        } else {
            Err(CoreError::BadUri(value))
        }
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl std::fmt::Display for RegistryUri {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn assets_accept_protocol_ids_and_refuse_injection() {
        assert!(AssetId::new("LP:NGN/KES:fpmm").is_ok());
        assert!(AssetId::new("REV").is_ok());
        assert!(AssetId::new("').inject").is_err());
        assert!(AssetId::new("a\"b").is_err());
        assert!(AssetId::new("").is_err());
    }

    #[test]
    fn currencies_accept_codes_only() {
        assert!(Currency::new("NGN").is_ok());
        assert!(Currency::new("n").is_err());
        assert!(Currency::new("NGN!").is_err());
    }

    #[test]
    fn uris_must_be_registry_uris() {
        assert!(RegistryUri::new("rho:id:abc123").is_ok());
        assert!(RegistryUri::new("http://example.com").is_err());
        assert!(RegistryUri::new("rho:id:`").is_err());
    }
}
