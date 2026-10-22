//! Chain-client errors.
//!
//! The variants distinguish the cases a caller must not conflate: a request that never
//! reached the node is safe to retry, a deploy the node refused is safe to retry, a deploy
//! that executed and reverted charged phlo and changed nothing, and a deploy whose fate is
//! unknown must not be retried blindly.

use rcash_core::CoreError;

/// An error from deploy construction, signing or node communication.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum ChainError {
    #[error(transparent)]
    Core(#[from] CoreError),
    #[error("invalid key: {0}")]
    BadKey(String),
    #[error("invalid hex: {0}")]
    BadHex(String),
    #[error("signing failed: {0}")]
    Crypto(String),
    #[error("network error: {0}")]
    Transport(String),
    #[error("node returned HTTP {status}: {body}")]
    Http { status: u16, body: String },
    #[error("could not decode the node response: {0}")]
    Decode(String),
    #[error("the node rejected the deploy: {0}")]
    DeployRejected(String),
    #[error("the deploy executed and failed: {error}")]
    DeployFailed {
        error: String,
        block_hash: Option<String>,
    },
    #[error("the deploy is still unknown after the timeout (last status: {last}); do not retry a value-moving deploy blindly")]
    StillUnknown { deploy_id: String, last: String },
    #[error("keystore error: {0}")]
    Keystore(String),
}

impl From<serde_json::Error> for ChainError {
    fn from(value: serde_json::Error) -> Self {
        ChainError::Decode(value.to_string())
    }
}
