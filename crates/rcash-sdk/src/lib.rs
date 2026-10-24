//! The R-Cash SDK.
//!
//! R0a establishes the client and the deploy lifecycle; the typed protocol operations
//! (account, vault, pool, transfer, oracle) are added in R1/R2 on top of this core.

use rcash_chain::deploy::DeployOptions;
use rcash_chain::node::{DeployStatus, NodeClient};
use rcash_chain::poll::PollPolicy;
use rcash_chain::rho_expr::{Reply, RhoValue};
use rcash_chain::{ChainError, KeyPair, SignedDeploy};
use rcash_core::manifest::Manifest;
use rcash_core::CoreError;

mod reads;
mod terms;
mod v4;
mod writes;

pub use rcash_chain::rho_expr::{Reply as ProtocolReply, RhoValue as ProtocolValue};
pub use reads::{Balances, FxRate, PriceFeed, Quote, QuoteAdd, Reserves, TransferInfo};
pub use v4::{V4Currency, V4Lock, V4Market, V4Quote, V4Reserves, V4Sent, V4Slot, V4Transfer};
pub use writes::{SwapResult, TxResult};

pub use rcash_chain;

/// A write-ahead signed deploy used for idempotent retries.
#[cfg(not(target_arch = "wasm32"))]
#[derive(serde::Serialize, serde::Deserialize)]
struct CachedDeploy {
    term: String,
    deploy_id: String,
    body: String,
}

/// A connected, signing client.
pub struct Client {
    node: NodeClient,
    key: Option<KeyPair>,
    shard_id: String,
    phlo_price: i64,
    phlo_limit: i64,
    poll: PollPolicy,
    manifest: Option<Manifest>,
    v4_manifest: Option<rcash_core::manifest::V4Manifest>,
}

impl std::fmt::Debug for Client {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Client")
            .field("node", &self.node)
            .field("key", &self.key)
            .field("shard_id", &self.shard_id)
            .finish()
    }
}

/// What happened to a submitted deploy.
#[derive(Clone, Debug)]
pub struct DeployOutcome {
    pub deploy_id: String,
    pub status: DeployStatus,
    /// True only when the node says the containing block is final.
    pub finalized: bool,
}

impl DeployOutcome {
    pub fn is_success(&self) -> bool {
        self.status.is_success()
    }

    pub fn block_hash(&self) -> Option<&str> {
        self.status.block().map(|b| b.block_hash.as_str())
    }
}

impl Client {
    /// Connect to a node with a key and devnet defaults.
    pub fn new(node_url: impl Into<String>, key: KeyPair) -> Result<Self, ChainError> {
        let node = NodeClient::new(node_url)?;
        Ok(Self {
            node,
            key: Some(key),
            shard_id: "/root".to_string(),
            phlo_price: 1,
            phlo_limit: 1_000_000,
            poll: PollPolicy::default(),
            manifest: None,
            v4_manifest: None,
        })
    }

    /// Connect for public reads only. Signed operations fail with a clear error.
    pub fn reader(node_url: impl Into<String>) -> Result<Self, ChainError> {
        Ok(Self {
            node: NodeClient::new(node_url)?,
            key: None,
            shard_id: "/root".to_string(),
            phlo_price: 1,
            phlo_limit: 1_000_000,
            poll: PollPolicy::default(),
            manifest: None,
            v4_manifest: None,
        })
    }

    /// Attach the deployment manifest used by typed reads.
    pub fn with_manifest(mut self, manifest: Manifest) -> Self {
        self.manifest = Some(manifest);
        self
    }

    /// The manifest, if one is attached.
    pub fn manifest(&self) -> Option<&Manifest> {
        self.manifest.as_ref()
    }

    pub(crate) fn require_manifest(&self) -> Result<&Manifest, ChainError> {
        self.manifest.as_ref().ok_or_else(|| {
            ChainError::Core(CoreError::BadManifest(
                "client has no deployment manifest; load deployments/devnet.json".into(),
            ))
        })
    }

    pub fn with_phlo(mut self, limit: i64, price: i64) -> Self {
        self.phlo_limit = limit;
        self.phlo_price = price;
        self
    }

    pub fn with_shard(mut self, shard: impl Into<String>) -> Self {
        self.shard_id = shard.into();
        self
    }

    pub fn with_poll(mut self, poll: PollPolicy) -> Self {
        self.poll = poll;
        self
    }

    pub fn node(&self) -> &NodeClient {
        &self.node
    }

    pub fn key(&self) -> Option<&KeyPair> {
        self.key.as_ref()
    }

    fn signing_key(&self) -> Result<&KeyPair, ChainError> {
        self.key
            .as_ref()
            .ok_or_else(|| ChainError::BadKey("this client has no signing key (read-only)".into()))
    }

    pub fn address(&self) -> Result<String, ChainError> {
        self.signing_key()?.rev_address()
    }

    /// Sign a term as a deploy without submitting it.
    ///
    /// `valid_after_block_number` anchors the deploy's 50-block lifespan; pass the current
    /// tip, not 0, or the node pools a deploy that can never be proposed.
    pub fn sign_term(
        &self,
        term: &str,
        valid_after_block_number: i64,
    ) -> Result<SignedDeploy, ChainError> {
        let data = DeployOptions::new(term)
            .shard_id(self.shard_id.clone())
            .valid_after_block_number(valid_after_block_number)
            .phlo(self.phlo_limit, self.phlo_price)
            .build()?;
        self.signing_key()?.sign_deploy(data)
    }

    /// Submit a term and wait until it is processed and its block is final.
    pub async fn deploy_term(&self, term: &str) -> Result<DeployOutcome, ChainError> {
        let tip = self.node.latest_block_number().await?;
        let signed = self.sign_term(term, tip)?;
        let deploy_id = self.node.deploy(&signed).await?;
        let status = self.node.wait_processed(&deploy_id, self.poll).await?;
        let mut finalized = false;
        if let Some(block) = status.block() {
            finalized = self
                .node
                .wait_finalized(&block.block_hash, self.poll)
                .await
                .is_ok();
        }
        Ok(DeployOutcome {
            deploy_id,
            status,
            finalized,
        })
    }

    /// Submit a term under an operation id, reusing the exact signed bytes on retry.
    ///
    /// The cache is a write-ahead record: the request body and deploy id are written
    /// before the POST. A retry checks `deploy-status` first and only resubmits when the
    /// deploy is still pooled or unknown; a duplicate is treated as already accepted.
    /// A cached entry signed for a different term is a hard error.
    ///
    /// A deploy rejected by a merge cannot be re-included. The caller must prove the
    /// effect absent at a finalized block, then delete the entry and use a **new**
    /// operation id so a fresh deploy is signed.
    #[cfg(not(target_arch = "wasm32"))]
    pub async fn deploy_term_cached(
        &self,
        term: &str,
        op: &str,
        cache_dir: &std::path::Path,
    ) -> Result<DeployOutcome, ChainError> {
        let safe: String = op
            .chars()
            .map(|c| {
                if c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.') {
                    c
                } else {
                    '_'
                }
            })
            .collect();
        if safe.is_empty() {
            return Err(ChainError::Decode("empty operation id".into()));
        }
        std::fs::create_dir_all(cache_dir)
            .map_err(|e| ChainError::Transport(format!("op cache: {e}")))?;
        let path = cache_dir.join(format!("{safe}.json"));
        let cached: Option<CachedDeploy> = match std::fs::read(&path) {
            Ok(bytes) => Some(
                serde_json::from_slice(&bytes)
                    .map_err(|e| ChainError::Decode(format!("op cache: {e}")))?,
            ),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
            Err(e) => return Err(ChainError::Transport(format!("op cache: {e}"))),
        };

        let deploy_id = match cached {
            Some(entry) => {
                if entry.term != term {
                    return Err(ChainError::Decode(format!(
                        "operation '{op}' was signed for a different term; refusing to reuse it"
                    )));
                }
                match self.node.deploy_status(&entry.deploy_id).await {
                    Ok(status) if status.is_processed() => {
                        return self.finish_outcome(entry.deploy_id, status).await;
                    }
                    Ok(_) | Err(ChainError::Decode(_)) => {
                        match self
                            .node
                            .deploy_body(&entry.body, &entry.deploy_id, entry.term.len())
                            .await
                        {
                            Ok(()) | Err(ChainError::Duplicate { .. }) => {}
                            Err(e) => return Err(e),
                        }
                    }
                    Err(ChainError::Transport(_))
                    | Err(ChainError::RateLimited { .. })
                    | Err(ChainError::Unavailable { .. }) => {
                        return Err(ChainError::Transport(
                            "op cache: node status unavailable; retry the operation".into(),
                        ));
                    }
                    Err(e) => return Err(e),
                }
                entry.deploy_id
            }
            None => {
                let tip = self.node.latest_block_number().await?;
                let signed = self.sign_term(term, tip)?;
                let body = serde_json::to_string(&signed.request_body())?;
                let entry = CachedDeploy {
                    term: term.to_string(),
                    deploy_id: signed.deploy_id.clone(),
                    body: body.clone(),
                };
                let bytes = serde_json::to_vec(&entry)?;
                let tmp = path.with_extension("json.tmp");
                std::fs::write(&tmp, bytes)
                    .map_err(|e| ChainError::Transport(format!("op cache: {e}")))?;
                std::fs::rename(&tmp, &path)
                    .map_err(|e| ChainError::Transport(format!("op cache: {e}")))?;
                match self
                    .node
                    .deploy_body(&body, &signed.deploy_id, term.len())
                    .await
                {
                    Ok(()) | Err(ChainError::Duplicate { .. }) => {}
                    Err(e) => return Err(e),
                }
                signed.deploy_id
            }
        };

        let status = self.node.wait_processed(&deploy_id, self.poll).await?;
        self.finish_outcome(deploy_id, status).await
    }

    #[cfg(not(target_arch = "wasm32"))]
    async fn finish_outcome(
        &self,
        deploy_id: String,
        status: DeployStatus,
    ) -> Result<DeployOutcome, ChainError> {
        let mut finalized = false;
        if let Some(block) = status.block() {
            finalized = self
                .node
                .wait_finalized(&block.block_hash, self.poll)
                .await
                .is_ok();
        }
        Ok(DeployOutcome {
            deploy_id,
            status,
            finalized,
        })
    }

    /// Submit a term without waiting.
    pub async fn submit_term(&self, term: &str) -> Result<String, ChainError> {
        let tip = self.node.latest_block_number().await?;
        let signed = self.sign_term(term, tip)?;
        self.node.deploy(&signed).await
    }

    /// Wait for a previously submitted deploy id.
    pub async fn wait(&self, deploy_id: &str) -> Result<DeployStatus, ChainError> {
        self.node.wait_processed(deploy_id, self.poll).await
    }

    /// The current finalized tip height, for absolute transfer expiries.
    pub async fn height(&self) -> Result<i64, ChainError> {
        self.node.latest_block_number().await
    }

    /// Run a public read and decode the protocol reply it returns.
    pub(crate) async fn explore_reply(&self, term: &str) -> Result<Reply, ChainError> {
        let response = self.node.explore(term).await?;
        let first = response
            .expr
            .first()
            .ok_or_else(|| ChainError::Decode("explore-deploy returned no value".into()))?;
        Reply::from_value(&RhoValue::decode(first)?)
    }

    /// Run a public read and decode the raw value (for arms that do not reply as
    /// `(true, …)`), or `None` when the term produced no value.
    pub(crate) async fn explore_value(&self, term: &str) -> Result<Option<RhoValue>, ChainError> {
        let response = self.node.explore(term).await?;
        match response.expr.first() {
            Some(value) => Ok(Some(RhoValue::decode(value)?)),
            None => Ok(None),
        }
    }

    /// Run a signed read and decode the raw value it sent to `deployId`.
    pub(crate) async fn signed_value(&self, term: &str) -> Result<RhoValue, ChainError> {
        let outcome = self.deploy_term(term).await?;
        match &outcome.status {
            DeployStatus::ProcessedWithSuccess { deploy_result, .. } => {
                let first = deploy_result.first().ok_or_else(|| {
                    ChainError::Decode("the deploy succeeded but returned no value".into())
                })?;
                RhoValue::decode(first)
            }
            DeployStatus::ProcessedWithError {
                deploy_error,
                block,
            } => Err(ChainError::DeployFailed {
                error: deploy_error.clone(),
                block_hash: Some(block.block_hash.clone()),
            }),
            DeployStatus::NotProcessed { status } => Err(ChainError::StillUnknown {
                deploy_id: outcome.deploy_id.clone(),
                last: status.clone(),
            }),
        }
    }
}
