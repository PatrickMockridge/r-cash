//! The R-Cash SDK.
//!
//! R0a establishes the client and the deploy lifecycle; the typed protocol operations
//! (account, vault, pool, transfer, oracle) are added in R1/R2 on top of this core.

use rcash_chain::deploy::DeployOptions;
use rcash_chain::node::{DeployStatus, NodeClient};
use rcash_chain::poll::PollPolicy;
use rcash_chain::{ChainError, KeyPair, SignedDeploy};

pub use rcash_chain;

/// A connected, signing client.
pub struct Client {
    node: NodeClient,
    key: KeyPair,
    shard_id: String,
    phlo_price: i64,
    phlo_limit: i64,
    poll: PollPolicy,
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
            key,
            shard_id: "/root".to_string(),
            phlo_price: 1,
            phlo_limit: 1_000_000,
            poll: PollPolicy::default(),
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

    pub fn key(&self) -> &KeyPair {
        &self.key
    }

    pub fn address(&self) -> Result<String, ChainError> {
        self.key.rev_address()
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
        self.key.sign_deploy(data)
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
}
