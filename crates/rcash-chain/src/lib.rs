//! Chain integration: deploy data, signing, REV addresses and the rnode HTTP API.
//!
//! The signing path deliberately calls the node's own crates
//! (`rchain_models::casper::protocol::casper_message::DeployData` and
//! `rchain_crypto::signatures::Signed`) rather than reimplementing the protobuf or the
//! hash. R0a's parity tests pin the result.

pub mod address;
pub mod claim;
pub mod deploy;
pub mod error;
pub mod keystore;
pub mod poll;
pub mod rho_expr;
pub mod sign;

pub mod node;

pub use address::{
    eth_address_from_public_key, rev_address_from_eth_address, rev_address_from_public_key,
};
pub use deploy::{DeployOptions, MAX_DEPLOY_TERM_BYTES};
pub use error::ChainError;
pub use sign::{KeyPair, SignedDeploy};

/// The pinned node crate revision.
pub const NODE_COMMIT: &str = "e2d073dcd02f1e560ccb84749937138a1e184b0b";
