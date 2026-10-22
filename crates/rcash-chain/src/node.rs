//! The rnode HTTP client.
//!
//! Verified against `node/src/web/http.rs` and `node/src/api/dto.rs`:
//! - `POST /api/v1/deploy` takes `{data, deployer, signature, sigAlgorithm}`.
//! - `GET /api/v1/deploy-status/{sig}` returns an externally tagged status enum.
//! - Finality is a separate route: `GET /api/is-finalized/{blockHash}`.
//! - `POST /api/v1/explore-deploy` takes a bare JSON string and does not bind
//!   `deployerId`.
//! - The public API enables permissive CORS; the admin API does not.

use std::time::{Duration, Instant};

use serde::Deserialize;

use crate::error::ChainError;
use crate::poll::PollPolicy;
use crate::sign::SignedDeploy;

/// A block summary, reduced to the fields a client needs.
#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BlockInfo {
    pub block_hash: String,
    pub block_number: i64,
    #[serde(default)]
    pub shard_id: String,
    #[serde(default)]
    pub timestamp: i64,
}

/// The deploy execution status returned by the node.
#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all_fields = "camelCase")]
pub enum DeployStatus {
    ProcessedWithSuccess {
        deploy_result: Vec<serde_json::Value>,
        block: BlockInfo,
    },
    ProcessedWithError {
        deploy_error: String,
        block: BlockInfo,
    },
    NotProcessed {
        status: String,
    },
}

impl DeployStatus {
    pub fn is_success(&self) -> bool {
        matches!(self, DeployStatus::ProcessedWithSuccess { .. })
    }

    pub fn is_processed(&self) -> bool {
        !matches!(self, DeployStatus::NotProcessed { .. })
    }

    pub fn block(&self) -> Option<&BlockInfo> {
        match self {
            DeployStatus::ProcessedWithSuccess { block, .. }
            | DeployStatus::ProcessedWithError { block, .. } => Some(block),
            DeployStatus::NotProcessed { .. } => None,
        }
    }

    pub fn deploy_error(&self) -> Option<&str> {
        match self {
            DeployStatus::ProcessedWithError { deploy_error, .. } => Some(deploy_error),
            _ => None,
        }
    }

    pub fn status_text(&self) -> String {
        match self {
            DeployStatus::ProcessedWithSuccess { .. } => "processedWithSuccess".into(),
            DeployStatus::ProcessedWithError { .. } => "processedWithError".into(),
            DeployStatus::NotProcessed { status } => format!("notProcessed: {status}"),
        }
    }
}

/// The response to `POST /api/v1/explore-deploy`.
#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExploreResponse {
    pub expr: Vec<serde_json::Value>,
    pub block: BlockInfo,
    #[serde(default)]
    pub reply_source: String,
}

/// A client for one rnode's public HTTP API.
#[derive(Clone)]
pub struct NodeClient {
    base: String,
    http: reqwest::Client,
}

impl std::fmt::Debug for NodeClient {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "NodeClient({})", self.base)
    }
}

impl NodeClient {
    /// Create a client for `base` (for example `http://localhost:40403`).
    pub fn new(base: impl Into<String>) -> Result<Self, ChainError> {
        let base = base.into().trim_end_matches('/').to_string();
        if base.is_empty() {
            return Err(ChainError::Transport("node URL is empty".into()));
        }
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .map_err(|e| ChainError::Transport(e.to_string()))?;
        Ok(Self { base, http })
    }

    pub fn base_url(&self) -> &str {
        &self.base
    }

    async fn send(&self, request: reqwest::RequestBuilder) -> Result<String, ChainError> {
        let response = request
            .send()
            .await
            .map_err(|e| ChainError::Transport(e.to_string()))?;
        let status = response.status();
        let body = response
            .text()
            .await
            .map_err(|e| ChainError::Transport(e.to_string()))?;
        if !status.is_success() {
            return Err(ChainError::Http {
                status: status.as_u16(),
                body,
            });
        }
        Ok(body)
    }

    /// `GET /api/v1/status`.
    pub async fn status(&self) -> Result<serde_json::Value, ChainError> {
        let body = self
            .send(self.http.get(format!("{}/api/v1/status", self.base)))
            .await?;
        serde_json::from_str(&body).map_err(Into::into)
    }

    /// The tip's block number, read from `/api/v1/status`.
    ///
    /// Deploys are anchored at the tip: `validAfterBlockNumber` starts the deploy's
    /// 50-block lifespan, so a deploy anchored at genesis is already expired.
    pub async fn latest_block_number(&self) -> Result<i64, ChainError> {
        let status = self.status().await?;
        status
            .get("latestBlockNumber")
            .and_then(serde_json::Value::as_i64)
            .ok_or_else(|| ChainError::Decode("status has no latestBlockNumber".into()))
    }

    /// Submit a signed deploy. Returns its locally computed deploy id.
    ///
    /// The node's success message embeds the same id; the client does not parse prose.
    pub async fn deploy(&self, signed: &SignedDeploy) -> Result<String, ChainError> {
        let body = signed.request_body();
        let response = self
            .http
            .post(format!("{}/api/v1/deploy", self.base))
            .json(&body)
            .send()
            .await
            .map_err(|e| ChainError::Transport(e.to_string()))?;
        let status = response.status();
        let text = response
            .text()
            .await
            .map_err(|e| ChainError::Transport(e.to_string()))?;
        if !status.is_success() {
            return Err(ChainError::DeployRejected(text));
        }
        Ok(signed.deploy_id.clone())
    }

    /// `GET /api/v1/deploy-status/{signature}`.
    pub async fn deploy_status(&self, deploy_id: &str) -> Result<DeployStatus, ChainError> {
        let body = self
            .send(
                self.http
                    .get(format!("{}/api/v1/deploy-status/{deploy_id}", self.base)),
            )
            .await?;
        serde_json::from_str(&body).map_err(Into::into)
    }

    /// Poll until the deploy is processed (success or error) or the timeout expires.
    pub async fn wait_processed(
        &self,
        deploy_id: &str,
        policy: PollPolicy,
    ) -> Result<DeployStatus, ChainError> {
        let start = Instant::now();
        let mut last = "no status yet".to_string();
        loop {
            if start.elapsed() >= policy.timeout {
                return Err(ChainError::StillUnknown {
                    deploy_id: deploy_id.to_string(),
                    last,
                });
            }
            match self.deploy_status(deploy_id).await {
                Ok(status) if status.is_processed() => return Ok(status),
                Ok(DeployStatus::NotProcessed { status }) => last = status,
                Ok(_) => unreachable!("is_processed covers every other variant"),
                Err(ChainError::Transport(e)) => last = e,
                Err(e) => return Err(e),
            }
            tokio::time::sleep(policy.interval).await;
        }
    }

    /// `GET /api/is-finalized/{blockHash}`.
    pub async fn is_finalized(&self, block_hash: &str) -> Result<bool, ChainError> {
        let body = self
            .send(
                self.http
                    .get(format!("{}/api/is-finalized/{block_hash}", self.base)),
            )
            .await?;
        serde_json::from_str(&body).map_err(Into::into)
    }

    /// Poll until the block is final.
    pub async fn wait_finalized(
        &self,
        block_hash: &str,
        policy: PollPolicy,
    ) -> Result<(), ChainError> {
        let start = Instant::now();
        let mut last = "not final".to_string();
        loop {
            if start.elapsed() >= policy.timeout {
                return Err(ChainError::StillUnknown {
                    deploy_id: block_hash.to_string(),
                    last,
                });
            }
            match self.is_finalized(block_hash).await {
                Ok(true) => return Ok(()),
                Ok(false) => last = "not final".to_string(),
                Err(ChainError::Transport(e)) => last = e,
                Err(e) => return Err(e),
            }
            tokio::time::sleep(policy.interval).await;
        }
    }

    /// `POST /api/v1/explore-deploy` with a bare JSON string term.
    ///
    /// This does not bind `deployerId`, so owner-authenticated reads cannot use it.
    pub async fn explore(&self, term: &str) -> Result<ExploreResponse, ChainError> {
        let body = self
            .send(
                self.http
                    .post(format!("{}/api/v1/explore-deploy", self.base))
                    .json(term),
            )
            .await?;
        serde_json::from_str(&body).map_err(Into::into)
    }

    /// `POST /api/v1/faucet` with a REV address.
    pub async fn faucet(&self, address: &str) -> Result<serde_json::Value, ChainError> {
        let body = self
            .send(
                self.http
                    .post(format!("{}/api/v1/faucet", self.base))
                    .json(&serde_json::json!({ "address": address })),
            )
            .await?;
        serde_json::from_str(&body).map_err(Into::into)
    }

    /// `GET /api/last-finalized-block`.
    pub async fn last_finalized_block(&self) -> Result<BlockInfo, ChainError> {
        let body = self
            .send(
                self.http
                    .get(format!("{}/api/last-finalized-block", self.base)),
            )
            .await?;
        serde_json::from_str(&body).map_err(Into::into)
    }

    /// `GET /api/v1/block/{hash}`.
    pub async fn block(&self, hash: &str) -> Result<serde_json::Value, ChainError> {
        let body = self
            .send(self.http.get(format!("{}/api/v1/block/{hash}", self.base)))
            .await?;
        serde_json::from_str(&body).map_err(Into::into)
    }
}
