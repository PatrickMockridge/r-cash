//! The rnode HTTP client.
//!
//! Verified against `node/src/web/http.rs` and `node/src/api/dto.rs`:
//! - `POST /api/v1/deploy` takes `{data, deployer, signature, sigAlgorithm}`.
//! - `GET /api/v1/deploy-status/{sig}` returns an externally tagged status enum.
//! - Finality is a separate route: `GET /api/is-finalized/{blockHash}`.
//! - `POST /api/v1/explore-deploy` takes a bare JSON string and does not bind
//!   `deployerId`; `rho:block:data` reports height 0 there.
//! - The public API enables permissive CORS; the admin API does not.

use std::sync::Arc;
use std::time::Duration;

#[cfg(not(target_arch = "wasm32"))]
use std::time::Instant;
#[cfg(target_arch = "wasm32")]
use web_time::Instant;

use serde::Deserialize;

use crate::error::ChainError;
use crate::poll::PollPolicy;
use crate::sign::SignedDeploy;

pub mod transport;

use transport::{HttpRequest, Method, Transport};

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
    transport: Arc<dyn Transport>,
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
        #[cfg(target_arch = "wasm32")]
        let transport: Arc<dyn Transport> = Arc::new(transport::WasmTransport);
        #[cfg(not(target_arch = "wasm32"))]
        let transport: Arc<dyn Transport> = Arc::new(transport::NativeTransport::new()?);
        Ok(Self { base, transport })
    }

    /// Build a client with a caller-supplied transport (tests, alternate backends).
    pub fn with_transport(
        base: impl Into<String>,
        transport: Arc<dyn Transport>,
    ) -> Result<Self, ChainError> {
        let base = base.into().trim_end_matches('/').to_string();
        if base.is_empty() {
            return Err(ChainError::Transport("node URL is empty".into()));
        }
        Ok(Self { base, transport })
    }

    pub fn base_url(&self) -> &str {
        &self.base
    }

    async fn request(
        &self,
        method: Method,
        path: &str,
        body: Option<String>,
    ) -> Result<String, ChainError> {
        let response = self
            .transport
            .send(HttpRequest {
                method,
                url: format!("{}{path}", self.base),
                body,
            })
            .await?;
        if !(200..300).contains(&response.status) {
            return Err(ChainError::Http {
                status: response.status,
                body: response.body,
            });
        }
        Ok(response.body)
    }

    /// `GET /api/v1/status`.
    pub async fn status(&self) -> Result<serde_json::Value, ChainError> {
        let body = self.request(Method::Get, "/api/v1/status", None).await?;
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
    pub async fn deploy(&self, signed: &SignedDeploy) -> Result<String, ChainError> {
        let body = serde_json::to_string(&signed.request_body())?;
        let response = self
            .transport
            .send(HttpRequest {
                method: Method::Post,
                url: format!("{}/api/v1/deploy", self.base),
                body: Some(body),
            })
            .await?;
        if !(200..300).contains(&response.status) {
            return Err(ChainError::DeployRejected(response.body));
        }
        Ok(signed.deploy_id.clone())
    }

    /// `GET /api/v1/deploy-status/{signature}`.
    pub async fn deploy_status(&self, deploy_id: &str) -> Result<DeployStatus, ChainError> {
        let body = self
            .request(
                Method::Get,
                &format!("/api/v1/deploy-status/{deploy_id}"),
                None,
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
            sleep(policy.interval).await;
        }
    }

    /// `GET /api/is-finalized/{blockHash}`.
    pub async fn is_finalized(&self, block_hash: &str) -> Result<bool, ChainError> {
        let body = self
            .request(
                Method::Get,
                &format!("/api/is-finalized/{block_hash}"),
                None,
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
            sleep(policy.interval).await;
        }
    }

    /// `POST /api/v1/explore-deploy` with a bare JSON string term.
    ///
    /// This does not bind `deployerId`, and `rho:block:data` reports height 0.
    pub async fn explore(&self, term: &str) -> Result<ExploreResponse, ChainError> {
        let body = serde_json::to_string(term)?;
        let response = self
            .transport
            .send(HttpRequest {
                method: Method::Post,
                url: format!("{}/api/v1/explore-deploy", self.base),
                body: Some(body),
            })
            .await?;
        if !(200..300).contains(&response.status) {
            return Err(ChainError::Http {
                status: response.status,
                body: response.body,
            });
        }
        serde_json::from_str(&response.body).map_err(Into::into)
    }

    /// `POST /api/v1/faucet` with a REV address.
    pub async fn faucet(&self, address: &str) -> Result<serde_json::Value, ChainError> {
        let body = serde_json::to_string(&serde_json::json!({ "address": address }))?;
        let response = self
            .transport
            .send(HttpRequest {
                method: Method::Post,
                url: format!("{}/api/v1/faucet", self.base),
                body: Some(body),
            })
            .await?;
        if !(200..300).contains(&response.status) {
            return Err(ChainError::Http {
                status: response.status,
                body: response.body,
            });
        }
        serde_json::from_str(&response.body).map_err(Into::into)
    }

    /// `GET /api/last-finalized-block`.
    pub async fn last_finalized_block(&self) -> Result<BlockInfo, ChainError> {
        let body = self
            .request(Method::Get, "/api/last-finalized-block", None)
            .await?;
        // The route wraps the block: `{"blockInfo": {...}}`.
        #[derive(Deserialize)]
        struct Wrapped {
            #[serde(rename = "blockInfo")]
            block_info: BlockInfo,
        }
        let wrapped: Wrapped = serde_json::from_str(&body)?;
        Ok(wrapped.block_info)
    }

    /// `GET /api/v1/block/{hash}`.
    pub async fn block(&self, hash: &str) -> Result<serde_json::Value, ChainError> {
        let body = self
            .request(Method::Get, &format!("/api/v1/block/{hash}"), None)
            .await?;
        serde_json::from_str(&body).map_err(Into::into)
    }
}

async fn sleep(duration: Duration) {
    #[cfg(target_arch = "wasm32")]
    gloo_timers::future::TimeoutFuture::new(duration.as_millis() as u32).await;
    #[cfg(not(target_arch = "wasm32"))]
    tokio::time::sleep(duration).await;
}
