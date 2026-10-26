//! The rholo node HTTP client.
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

/// Map a non-2xx response to the retry class the caller must act on.
fn classify_http(status: u16, body: String, retry_after: Option<u64>) -> ChainError {
    match status {
        429 => ChainError::RateLimited { retry_after, body },
        503 => ChainError::Unavailable { retry_after, body },
        400 if body.to_ascii_lowercase().contains("admission") => {
            ChainError::AdmissionRefused { status, body }
        }
        _ => ChainError::Http { status, body },
    }
}

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

    /// The decoded deploy result on success.
    pub fn deploy_result(&self) -> Option<&[serde_json::Value]> {
        match self {
            DeployStatus::ProcessedWithSuccess { deploy_result, .. } => Some(deploy_result),
            _ => None,
        }
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

/// A client for one rholo node's public HTTP API.
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
            return Err(classify_http(
                response.status,
                response.body,
                response.retry_after,
            ));
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
        self.deploy_body(&body, &signed.deploy_id, signed.data.term.len())
            .await?;
        Ok(signed.deploy_id.clone())
    }

    /// Submit an exact request body. Used by the signed-deploy cache so a retry
    /// sends the same bytes and is refused before parse while the deploy is pooled.
    pub async fn deploy_body(
        &self,
        body: &str,
        deploy_id: &str,
        term_len: usize,
    ) -> Result<(), ChainError> {
        let response = self
            .transport
            .send(HttpRequest {
                method: Method::Post,
                url: format!("{}/api/v1/deploy", self.base),
                body: Some(body.to_string()),
            })
            .await?;
        if !(200..300).contains(&response.status) {
            let lower = response.body.to_ascii_lowercase();
            if lower.contains("duplicate")
                || (lower.contains("already") && lower.contains("deploy"))
            {
                return Err(ChainError::Duplicate {
                    deploy_id: deploy_id.to_string(),
                });
            }
            if lower.contains("term is") && lower.contains("bytes") {
                return Err(ChainError::TermTooLarge {
                    bytes: term_len,
                    limit: 64 * 1024,
                });
            }
            if response.status == 429 || response.status == 503 {
                return Err(classify_http(
                    response.status,
                    response.body,
                    response.retry_after,
                ));
            }
            return Err(ChainError::DeployRejected(response.body));
        }
        Ok(())
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
        let mut attempt = 0u32;
        loop {
            if start.elapsed() >= policy.timeout {
                return Err(ChainError::StillUnknown {
                    deploy_id: deploy_id.to_string(),
                    last,
                });
            }
            let mut retry_after = None;
            match self.deploy_status(deploy_id).await {
                Ok(status) if status.is_processed() => return Ok(status),
                Ok(DeployStatus::NotProcessed { status }) => last = status,
                Ok(_) => unreachable!("is_processed covers every other variant"),
                Err(ChainError::Transport(e)) => last = e,
                Err(ChainError::RateLimited {
                    retry_after: after,
                    body,
                })
                | Err(ChainError::Unavailable {
                    retry_after: after,
                    body,
                }) => {
                    retry_after = after;
                    last = body;
                }
                Err(e) => return Err(e),
            }
            let delay = policy.delay(attempt, deploy_id);
            let delay = match retry_after {
                Some(seconds) => delay.max(Duration::from_secs(seconds)),
                None => delay,
            };
            attempt = attempt.saturating_add(1);
            sleep(delay).await;
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
        let mut attempt = 0u32;
        loop {
            if start.elapsed() >= policy.timeout {
                return Err(ChainError::StillUnknown {
                    deploy_id: block_hash.to_string(),
                    last,
                });
            }
            let mut retry_after = None;
            match self.is_finalized(block_hash).await {
                Ok(true) => return Ok(()),
                Ok(false) => last = "not final".to_string(),
                Err(ChainError::Transport(e)) => last = e,
                Err(ChainError::RateLimited {
                    retry_after: after,
                    body,
                })
                | Err(ChainError::Unavailable {
                    retry_after: after,
                    body,
                }) => {
                    retry_after = after;
                    last = body;
                }
                Err(e) => return Err(e),
            }
            let delay = policy.delay(attempt, block_hash);
            let delay = match retry_after {
                Some(seconds) => delay.max(Duration::from_secs(seconds)),
                None => delay,
            };
            attempt = attempt.saturating_add(1);
            sleep(delay).await;
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
            return Err(classify_http(
                response.status,
                response.body,
                response.retry_after,
            ));
        }
        serde_json::from_str(&response.body).map_err(Into::into)
    }

    /// `POST /api/v1/explore-deploy-by-block-hash`.
    ///
    /// The body is camelCase (`term`, `blockHash`, `usePreStateHash`); snake_case is
    /// refused with 422. `use_pre_state=false` reads the block's post-state.
    pub async fn explore_at(
        &self,
        term: &str,
        block_hash: &str,
        use_pre_state: bool,
    ) -> Result<ExploreResponse, ChainError> {
        let body = serde_json::to_string(&serde_json::json!({
            "term": term,
            "blockHash": block_hash,
            "usePreStateHash": use_pre_state,
        }))?;
        let response = self
            .transport
            .send(HttpRequest {
                method: Method::Post,
                url: format!("{}/api/v1/explore-deploy-by-block-hash", self.base),
                body: Some(body),
            })
            .await?;
        if !(200..300).contains(&response.status) {
            return Err(classify_http(
                response.status,
                response.body,
                response.retry_after,
            ));
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
            return Err(classify_http(
                response.status,
                response.body,
                response.retry_after,
            ));
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

#[cfg(test)]
mod refusal_tests {
    use super::*;
    use async_trait::async_trait;
    use std::sync::Arc;
    use transport::{HttpRequest, HttpResponse, Transport};

    struct Fixed(Result<HttpResponse, ChainError>);

    #[async_trait(?Send)]
    impl Transport for Fixed {
        async fn send(&self, _request: HttpRequest) -> Result<HttpResponse, ChainError> {
            self.0.clone()
        }
    }

    fn client(status: u16, body: &str, retry_after: Option<u64>) -> NodeClient {
        let response = HttpResponse {
            status,
            body: body.to_string(),
            retry_after,
        };
        NodeClient::with_transport("http://node", Arc::new(Fixed(Ok(response)))).unwrap()
    }

    #[tokio::test]
    async fn a_429_is_a_rate_limit_not_a_generic_error() {
        let error = client(429, "too many", Some(2))
            .deploy_body("{}", "deadbeef", 10)
            .await
            .unwrap_err();
        assert!(matches!(
            error,
            ChainError::RateLimited {
                retry_after: Some(2),
                ..
            }
        ));
    }

    #[tokio::test]
    async fn a_503_is_shed_work_not_a_rejection() {
        let error = client(503, "throttled", Some(1))
            .deploy_body("{}", "deadbeef", 10)
            .await
            .unwrap_err();
        assert!(matches!(
            error,
            ChainError::Unavailable {
                retry_after: Some(1),
                ..
            }
        ));
    }

    #[tokio::test]
    async fn a_duplicate_body_names_the_deploy_id() {
        let error = client(400, "deploy already exists: duplicate", None)
            .deploy_body("{}", "deadbeef", 10)
            .await
            .unwrap_err();
        match error {
            ChainError::Duplicate { deploy_id } => assert_eq!(deploy_id, "deadbeef"),
            other => panic!("expected duplicate, got {other:?}"),
        }
    }

    #[tokio::test]
    async fn a_200_is_accepted() {
        client(200, "{}", None)
            .deploy_body("{}", "deadbeef", 10)
            .await
            .unwrap();
    }
}
