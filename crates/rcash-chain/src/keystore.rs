//! Devnet key files.
//!
//! This is the plaintext `.devnet/keys.json` format the harness already uses, not the
//! browser keystore. The encrypted Web3 Secret Storage v3 keystore for the wallet lives in
//! `rcash-wasm` (R3a); this type is for local devnet tooling only and is documented as
//! such.

use std::collections::BTreeMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::error::ChainError;
use crate::sign::KeyPair;

/// One named devnet key.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DevnetKey {
    pub name: String,
    pub secret: String,
    pub public: String,
    pub address: String,
    #[serde(default, skip_serializing_if = "is_false")]
    pub funded: bool,
}

fn is_false(value: &bool) -> bool {
    !*value
}

/// The `.devnet/keys.json` document: named keys, flattening to name → entry.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct DevnetKeys {
    #[serde(flatten)]
    pub keys: BTreeMap<String, DevnetKey>,
}

impl DevnetKeys {
    /// Read a keys file.
    pub fn load(path: impl AsRef<Path>) -> Result<Self, ChainError> {
        let text = std::fs::read_to_string(path.as_ref())
            .map_err(|e| ChainError::Keystore(format!("{}: {e}", path.as_ref().display())))?;
        serde_json::from_str(&text).map_err(|e| ChainError::Keystore(e.to_string()))
    }

    /// Write a keys file with owner-only permissions.
    pub fn save(&self, path: impl AsRef<Path>) -> Result<(), ChainError> {
        let text =
            serde_json::to_string_pretty(self).map_err(|e| ChainError::Keystore(e.to_string()))?;
        let path = path.as_ref();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| ChainError::Keystore(format!("{}: {e}", parent.display())))?;
        }
        std::fs::write(path, text)
            .map_err(|e| ChainError::Keystore(format!("{}: {e}", path.display())))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600));
        }
        Ok(())
    }

    /// Add a freshly generated key under `name`.
    pub fn insert_generated(&mut self, name: impl Into<String>) -> Result<&DevnetKey, ChainError> {
        let name = name.into();
        let key = KeyPair::generate()?;
        let entry = DevnetKey {
            name: name.clone(),
            secret: key.secret_hex(),
            public: key.public_hex(),
            address: key.rev_address()?,
            funded: false,
        };
        self.keys.insert(name.clone(), entry);
        Ok(&self.keys[&name])
    }

    /// Look up a key by name.
    pub fn key(&self, name: &str) -> Result<KeyPair, ChainError> {
        let entry = self
            .keys
            .get(name)
            .ok_or_else(|| ChainError::Keystore(format!("no key named {name}")))?;
        KeyPair::from_secret_hex(&entry.secret)
    }

    /// The first key in the file, if any.
    pub fn first_key(&self) -> Result<KeyPair, ChainError> {
        let (_, entry) = self
            .keys
            .iter()
            .next()
            .ok_or_else(|| ChainError::Keystore("the keys file is empty".into()))?;
        KeyPair::from_secret_hex(&entry.secret)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_the_harness_format() {
        let text = r#"{
            "deployer": {
                "name": "deployer",
                "secret": "a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76",
                "public": "04f700a417754b775d95421973bdbdadb2d23c8a5af46f1829b1431f5c136e549e8a0d61aa0c793f1a614f8e437711c7758473c6ceb0859ac7e9e07911ca66b5c4",
                "address": "11112VYAt8rUGNRRZX3eJdgagaAhtWTK8Js7F7X5iqddMVqyDTtYau"
            }
        }"#;
        let keys: DevnetKeys = serde_json::from_str(text).unwrap();
        let key = keys.key("deployer").unwrap();
        assert_eq!(key.public_hex().len(), 130);
        assert_eq!(keys.keys.len(), 1);
    }
}
