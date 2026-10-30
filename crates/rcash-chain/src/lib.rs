//! Chain integration: deploy data, signing, REV addresses and the rholo node HTTP API.
//!
//! The signing path deliberately calls the node's own crates
//! (the `DeployData` protobuf shape and `rchain_crypto`'s hash/signature functions)
//! rather than reimplementing the cryptography. R0a's parity tests pin the result.

pub mod address;
pub mod claim;
pub mod deploy;
pub mod error;
pub mod keystore;
pub mod poll;
pub mod rho_expr;
pub mod sign;

pub mod node;

pub use node::pool::{
    DiscoveryMode, DiscoveryReport, EndpointSource, NodeEndpoint, PoolOptions, WritePlan,
};

pub use address::{
    eth_address_from_public_key, rev_address_from_eth_address, rev_address_from_public_key,
};
pub use deploy::{DeployData, DeployOptions, MAX_DEPLOY_TERM_BYTES};
pub use error::ChainError;
pub use sign::{KeyPair, SignedDeploy};

/// Sign a protocol payload and return the DER signature as lowercase hex.
pub fn sign_payload_hex(key: &KeyPair, payload: &[u8]) -> Result<String, ChainError> {
    Ok(rchain_shared::base16::encode(&key.sign_payload(payload)?))
}

/// The pinned node crate revision.
pub const NODE_COMMIT: &str = "e2d073dcd02f1e560ccb84749937138a1e184b0b";
