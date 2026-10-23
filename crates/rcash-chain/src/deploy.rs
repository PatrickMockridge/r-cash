//! Deploy data construction.
//!
//! `DeployData` is declared here with the node's protobuf field tags. Using `rchain-models`
//! would invoke `protoc` (a C++ tool) at build time; the wire contract is the field tags,
//! and the parity tests pin the encoded bytes.

use prost::Message;
use rcash_core::rho::check_term_size;
use rchain_shared::serialize::Serialize as RhoSerialize;
use serde::{Deserialize, Serialize};

use crate::error::ChainError;

/// The fields of a deploy that are signed and submitted.
///
/// This is the node's `DeployDataProto` shape, re-declared locally so the client build
/// does not need `rchain-models` and therefore does not invoke `protoc` (a C++ tool).
/// The field tags are the wire contract; `deployer`, `sig` and `sigAlgorithm` are
/// deliberately absent.
#[derive(Clone, PartialEq, Eq, Message, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DeployData {
    #[prost(string, tag = "2")]
    pub term: String,
    #[prost(int64, tag = "3")]
    pub timestamp: i64,
    #[prost(int64, tag = "7")]
    pub phlo_price: i64,
    #[prost(int64, tag = "8")]
    pub phlo_limit: i64,
    #[prost(int64, tag = "10")]
    pub valid_after_block_number: i64,
    #[prost(string, tag = "11")]
    pub shard_id: String,
    #[prost(bytes = "vec", repeated, tag = "12")]
    #[serde(
        default,
        skip_serializing_if = "Vec::is_empty",
        with = "hex_attachments"
    )]
    pub attachments: Vec<Vec<u8>>,
}

impl RhoSerialize<DeployData> for DeployData {
    fn encode(a: &DeployData) -> Vec<u8> {
        a.encode_to_vec()
    }

    fn decode(bytes: &[u8]) -> Result<DeployData, String> {
        <DeployData as Message>::decode(bytes).map_err(|e| e.to_string())
    }
}

mod hex_attachments {
    use serde::{Deserialize, Deserializer, Serializer};

    pub fn serialize<S: Serializer>(value: &[Vec<u8>], s: S) -> Result<S::Ok, S::Error> {
        let hex: Vec<String> = value
            .iter()
            .map(|bytes| rchain_shared::base16::encode(bytes))
            .collect();
        s.collect_seq(hex)
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(d: D) -> Result<Vec<Vec<u8>>, D::Error> {
        let hex = Vec::<String>::deserialize(d)?;
        hex.into_iter()
            .map(|h| {
                rchain_shared::base16::decode(&h)
                    .ok_or_else(|| serde::de::Error::custom("attachment is not valid hex"))
            })
            .collect()
    }
}

/// The node's maximum deploy term size, inclusive.
pub const MAX_DEPLOY_TERM_BYTES: usize = 64 * 1024;

/// The fields of a deploy the caller controls.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeployOptions {
    pub term: String,
    pub timestamp: i64,
    pub phlo_price: i64,
    pub phlo_limit: i64,
    pub valid_after_block_number: i64,
    pub shard_id: String,
    pub attachments: Vec<Vec<u8>>,
}

impl DeployOptions {
    /// A deploy of `term` with devnet defaults (phlo 1, shard `root`).
    pub fn new(term: impl Into<String>) -> Self {
        Self {
            term: term.into(),
            timestamp: now_millis(),
            phlo_price: 1,
            phlo_limit: 1_000_000,
            valid_after_block_number: 0,
            shard_id: "/root".to_string(),
            attachments: Vec::new(),
        }
    }

    pub fn timestamp(mut self, timestamp: i64) -> Self {
        self.timestamp = timestamp;
        self
    }

    pub fn phlo(mut self, limit: i64, price: i64) -> Self {
        self.phlo_limit = limit;
        self.phlo_price = price;
        self
    }

    pub fn valid_after_block_number(mut self, number: i64) -> Self {
        self.valid_after_block_number = number;
        self
    }

    pub fn shard_id(mut self, shard: impl Into<String>) -> Self {
        self.shard_id = shard.into();
        self
    }

    pub fn attachments(mut self, attachments: Vec<Vec<u8>>) -> Self {
        self.attachments = attachments;
        self
    }

    /// Validate and produce the node's `DeployData`.
    pub fn build(self) -> Result<DeployData, ChainError> {
        check_term_size(&self.term)?;
        if self.term.trim().is_empty() {
            return Err(ChainError::Core(rcash_core::CoreError::BadManifest(
                "deploy term is empty".into(),
            )));
        }
        if self.shard_id.is_empty() {
            return Err(ChainError::Core(rcash_core::CoreError::BadManifest(
                "shard id is empty".into(),
            )));
        }
        if self.phlo_price < 0 || self.phlo_limit < 0 {
            return Err(ChainError::Core(rcash_core::CoreError::BadManifest(
                "phlo price and limit must be non-negative".into(),
            )));
        }
        Ok(DeployData {
            term: self.term,
            timestamp: self.timestamp,
            phlo_price: self.phlo_price,
            phlo_limit: self.phlo_limit,
            valid_after_block_number: self.valid_after_block_number,
            shard_id: self.shard_id,
            attachments: self.attachments,
        })
    }
}

/// Current wall-clock time in milliseconds since the Unix epoch.
///
/// Deploy timestamps are metadata; the protocol never uses them for economics.
/// `std::time` panics on wasm32-unknown-unknown, so the browser uses `web-time`.
pub fn now_millis() -> i64 {
    #[cfg(target_arch = "wasm32")]
    let duration = web_time::SystemTime::now().duration_since(web_time::UNIX_EPOCH);
    #[cfg(not(target_arch = "wasm32"))]
    let duration = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH);
    duration.map(|d| d.as_millis() as i64).unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use rchain_shared::serialize::Serialize;

    #[test]
    fn golden_bytes_match_the_node_for_an_empty_attachment_deploy() {
        // Term = "Nil", timestamp 0, phloPrice 1 (field 7), phloLimit 1 (field 8),
        // validAfterBlockNumber 0, shard "/root" (field 11), no attachments. Zero values
        // are omitted by prost, which is exactly what the node signs.
        let data = DeployOptions::new("Nil")
            .timestamp(0)
            .phlo(1, 1)
            .valid_after_block_number(0)
            .shard_id("/root")
            .build()
            .unwrap();
        let bytes = <DeployData as Serialize<DeployData>>::encode(&data);
        assert_eq!(
            rchain_shared::base16::encode(&bytes),
            "12034e696c380140015a052f726f6f74"
        );
    }

    #[test]
    fn an_attachment_is_field_12_and_deployer_sig_are_absent() {
        let data = DeployOptions::new("Nil")
            .timestamp(0)
            .phlo(1, 1)
            .shard_id("/root")
            .attachments(vec![vec![0xAA, 0xBB]])
            .build()
            .unwrap();
        let bytes = <DeployData as Serialize<DeployData>>::encode(&data);
        let hex = rchain_shared::base16::encode(&bytes);
        assert!(
            hex.ends_with("6202aabb"),
            "field 12 (0x62) must carry the attachment: {hex}"
        );
        assert!(
            !hex.starts_with("0a"),
            "deployer (field 1) must not be signed"
        );
        assert!(!hex.contains("2204"), "sig (field 4) must not be signed");
    }

    #[test]
    fn oversized_terms_are_refused_before_signing() {
        let term = "N".repeat(MAX_DEPLOY_TERM_BYTES + 1);
        assert!(DeployOptions::new(term).build().is_err());
        let term = "N".repeat(MAX_DEPLOY_TERM_BYTES);
        assert!(DeployOptions::new(term).build().is_ok());
    }
}
