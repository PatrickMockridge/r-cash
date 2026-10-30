//! The rholo node HTTP client.
//!
//! Verified against `node/src/web/http.rs` and `node/src/api/dto.rs`:
//! - `POST /api/v1/deploy` takes `{data, deployer, signature, sigAlgorithm}`.
//! - `GET /api/v1/deploy-status/{sig}` returns an externally tagged status enum.
//! - Finality is a separate route: `GET /api/is-finalized/{blockHash}`.
//! - `POST /api/v1/explore-deploy` takes a bare JSON string and does not bind
//!   `deployerId`; `rho:block:data` reports height 0 there.
//! - The public API enables permissive CORS; the admin API does not.
//!
//! One client can serve a pool of nodes. The seed's `GET /api/v1/nodes` (rholo Law 90)
//! is advisory; every entry is re-verified, reads may round-robin, and a signed deploy
//! is sent to exactly one node. A node that returns 404 for the hostlist leaves the
//! client behaving exactly as the old single-endpoint one.

use std::collections::BTreeSet;
use std::sync::{Arc, Mutex};
use std::time::Duration;

#[cfg(not(target_arch = "wasm32"))]
use std::time::Instant;
#[cfg(target_arch = "wasm32")]
use web_time::Instant;

use futures_util::stream::{self, StreamExt};
use serde::Deserialize;

use crate::error::ChainError;
use crate::poll::PollPolicy;
use crate::sign::SignedDeploy;

pub mod pool;
pub mod transport;

use pool::{
    best_write_tier, compute_anchor, dedupe_endpoints, explicit_endpoints, filter_node_list,
    filter_stale_targets, is_read_retryable, parse_node_list, rank_write_targets, verify_node,
    DiscoveryMode, DiscoveryReport, EndpointSource, NodeEndpoint, NodeStatusView, PoolOptions,
    PoolState, RejectedEntry, WritePlan, DEPLOY_LIFESPAN_BLOCKS, MAX_HOSTLIST_AGE_MS,
};
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
            DeployStatus::ProcessedWithSuccess { .. } | DeployStatus::NotProcessed { .. } => None,
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

/// A client for one rholo node's public HTTP API, optionally pooled with its hostlist.
#[derive(Clone)]
pub struct NodeClient {
    base: String,
    transport: Arc<dyn Transport>,
    pool: Arc<Mutex<PoolState>>,
}

impl std::fmt::Debug for NodeClient {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "NodeClient({})", self.base)
    }
}

impl NodeClient {
    /// Create a client for `base` (for example `http://localhost:40403`).
    ///
    /// Hostlist discovery is enabled; a node that does not publish one is used alone.
    pub fn new(base: impl Into<String>) -> Result<Self, ChainError> {
        Self::new_with_options(base, PoolOptions::default())
    }

    /// Create a client for `base` with explicit pool options.
    pub fn new_with_options(
        base: impl Into<String>,
        options: PoolOptions,
    ) -> Result<Self, ChainError> {
        #[cfg(target_arch = "wasm32")]
        let transport: Arc<dyn Transport> = Arc::new(transport::WasmTransport);
        #[cfg(not(target_arch = "wasm32"))]
        let transport: Arc<dyn Transport> = Arc::new(transport::NativeTransport::new()?);
        Self::with_options(base, transport, options)
    }

    /// Build a client with a caller-supplied transport (tests, alternate backends).
    ///
    /// Discovery is disabled so a fixture transport sees exactly the calls a test scripts.
    pub fn with_transport(
        base: impl Into<String>,
        transport: Arc<dyn Transport>,
    ) -> Result<Self, ChainError> {
        let options = PoolOptions {
            discovery: DiscoveryMode::Disabled,
            ..PoolOptions::default()
        };
        Self::with_options(base, transport, options)
    }

    /// Build a client with both a transport and explicit options.
    pub fn with_options(
        base: impl Into<String>,
        transport: Arc<dyn Transport>,
        options: PoolOptions,
    ) -> Result<Self, ChainError> {
        let base = base.into().trim_end_matches('/').to_string();
        if base.is_empty() {
            return Err(ChainError::Transport("node URL is empty".into()));
        }
        for raw in &options.explicit_nodes {
            if pool::normalize_base(raw).is_none() {
                return Err(ChainError::Transport(format!("invalid node URL: {raw}")));
            }
        }
        let pool = Arc::new(Mutex::new(PoolState::new(options, &base)));
        Ok(Self {
            base,
            transport,
            pool,
        })
    }

    pub fn base_url(&self) -> &str {
        &self.base
    }

    /// The shard every signed deploy carries, and the shard the pool filters for.
    pub fn set_expected_shard(&self, shard: impl Into<String>) {
        let shard = shard.into();
        let mut state = self.lock();
        if state.options.shard_id == shard {
            return;
        }
        state.options.shard_id = shard;
        state.fetched_at = None;
        state.negative_until = None;
        state
            .endpoints
            .retain(|endpoint| endpoint.source != EndpointSource::Hostlist);
    }

    /// The network id to require of hostlist entries. `None` adopts the seed's answer.
    pub fn set_expected_network(&self, network: impl Into<String>) {
        let mut state = self.lock();
        state.options.network_id = Some(network.into());
        state.fetched_at = None;
        state.negative_until = None;
    }

    /// Turn hostlist discovery on or off after construction.
    pub fn set_discovery(&self, mode: DiscoveryMode) {
        let mut state = self.lock();
        state.options.discovery = mode;
        state.fetched_at = None;
        state.negative_until = None;
        if mode == DiscoveryMode::Disabled {
            state
                .endpoints
                .retain(|endpoint| endpoint.source != EndpointSource::Hostlist);
        }
    }

    pub fn discovery_mode(&self) -> DiscoveryMode {
        self.lock().options.discovery
    }

    /// Replace the explicit endpoint list. Discovery, if enabled, adds to it.
    pub fn set_nodes(&self, nodes: Vec<String>) -> Result<(), ChainError> {
        let mut normalized = Vec::with_capacity(nodes.len());
        for raw in nodes {
            normalized.push(
                pool::normalize_base(&raw)
                    .ok_or_else(|| ChainError::Transport(format!("invalid node URL: {raw}")))?,
            );
        }
        let mut state = self.lock();
        state.options.explicit_nodes = normalized;
        let options = state.options.clone();
        let seed = self.base.clone();
        state.endpoints = fallback_endpoints(&options, &seed);
        state.fetched_at = None;
        state.negative_until = None;
        Ok(())
    }

    /// The endpoints currently known to the pool (the seed alone before discovery).
    pub fn nodes(&self) -> Vec<NodeEndpoint> {
        let state = self.lock();
        if state.endpoints.is_empty() {
            vec![NodeEndpoint::seed(&self.base)]
        } else {
            state.endpoints.clone()
        }
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, PoolState> {
        self.pool
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    async fn request_on(
        &self,
        base: &str,
        method: Method,
        path: &str,
        body: Option<String>,
        timeout: Option<Duration>,
    ) -> Result<String, ChainError> {
        let response = self
            .transport
            .send(HttpRequest {
                method,
                url: format!("{base}{path}"),
                body,
                timeout,
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

    /// A seed-only request. Discovery and status diagnostics use this so they cannot
    /// recurse through the pool.
    async fn seed_request(
        &self,
        method: Method,
        path: &str,
        body: Option<String>,
        timeout: Option<Duration>,
    ) -> Result<String, ChainError> {
        let base = self.base.clone();
        self.request_on(&base, method, path, body, timeout).await
    }

    /// `GET /api/v1/status` on the seed only, with no discovery.
    pub async fn seed_status(&self) -> Result<serde_json::Value, ChainError> {
        let body = self
            .seed_request(Method::Get, "/api/v1/status", None, None)
            .await?;
        serde_json::from_str(&body).map_err(Into::into)
    }

    async fn status_on(
        &self,
        base: &str,
        timeout: Option<Duration>,
    ) -> Result<NodeStatusView, ChainError> {
        let body = self
            .request_on(base, Method::Get, "/api/v1/status", None, timeout)
            .await?;
        serde_json::from_str(&body).map_err(Into::into)
    }

    async fn ensure_ready(&self) {
        let mode = self.lock().options.discovery;
        if mode == DiscoveryMode::Disabled {
            return;
        }
        {
            let mut state = self.lock();
            if state.fresh() || state.refreshing {
                return;
            }
            state.refreshing = true;
        }
        let result = self.refresh_snapshot().await;
        {
            let mut state = self.lock();
            state.refreshing = false;
            if let Err(error) = result {
                if state.report.is_none() {
                    state.report = Some(DiscoveryReport {
                        unsupported: false,
                        fallback_to_seed: true,
                        network_id: None,
                        primary_shard: None,
                        generated_at: None,
                        generated_age_ms: None,
                        endpoints: state.endpoints.clone(),
                        rejected: Vec::new(),
                        error: Some(error.to_string()),
                    });
                }
            }
        }
    }

    /// Force a discovery cycle and return its report. Lazy operations ignore failures;
    /// this call returns the typed reason.
    pub async fn discover(&self) -> Result<DiscoveryReport, ChainError> {
        self.refresh_snapshot().await
    }

    /// Probe the operator-supplied endpoints and the seed. This is what makes the
    /// cost/speed ranking meaningful when the seed publishes no hostlist at all.
    async fn probe_known(
        &self,
        options: &PoolOptions,
        seed: &str,
        exclude: &BTreeSet<String>,
        include_seed: bool,
    ) -> Vec<NodeEndpoint> {
        let mut bases: Vec<(String, EndpointSource)> = Vec::new();
        let mut seen = BTreeSet::new();
        for raw in &options.explicit_nodes {
            let Some(base) = pool::normalize_base(raw) else {
                continue;
            };
            if !pool::scheme_allowed(&base, seed) {
                continue;
            }
            if exclude.contains(&base) || !seen.insert(base.clone()) {
                continue;
            }
            bases.push((base, EndpointSource::Explicit));
        }
        let seed_base = self.base.clone();
        if include_seed
            && pool::scheme_allowed(&seed_base, seed)
            && !exclude.contains(&seed_base)
            && seen.insert(seed_base.clone())
        {
            bases.push((seed_base, EndpointSource::Seed));
        }

        let client = self;
        let options = options.clone();
        let probes = bases.into_iter().map(|(base, source)| {
            let options = options.clone();
            async move {
                match client.status_on(&base, Some(options.probe_timeout)).await {
                    Ok(status) => NodeEndpoint {
                        base,
                        node_id: (!status.address.is_empty()).then(|| status.address.clone()),
                        network_id: (!status.network_id.is_empty())
                            .then(|| status.network_id.clone()),
                        shard_id: (!status.shard_id.is_empty()).then(|| status.shard_id.clone()),
                        latest_block_number: status.latest_block_number,
                        min_phlo_price: status.min_phlo_price,
                        accepts_deploys: status.accepts_deploys.unwrap_or(true),
                        proposer: status.proposer.unwrap_or(true),
                        node_version: None,
                        is_self: false,
                        source,
                    },
                    Err(_) => NodeEndpoint {
                        // A node that cannot answer status is not a first choice, but it
                        // stays in the list so a later probe can recover it.
                        accepts_deploys: false,
                        source,
                        ..NodeEndpoint::seed(&base)
                    },
                }
            }
        });
        stream::iter(probes).buffer_unordered(8).collect().await
    }

    async fn refresh_snapshot(&self) -> Result<DiscoveryReport, ChainError> {
        let (options, seed) = {
            let state = self.lock();
            (state.options.clone(), self.base.clone())
        };

        let body = match self
            .seed_request(
                Method::Get,
                "/api/v1/nodes",
                None,
                Some(options.probe_timeout),
            )
            .await
        {
            Ok(body) => body,
            Err(ChainError::Http { status: 404, .. }) => {
                let known = self
                    .probe_known(&options, &seed, &BTreeSet::new(), true)
                    .await;
                self.apply_failure(
                    &options,
                    true,
                    "the node does not publish a deploy hostlist",
                    known,
                );
                return Err(ChainError::HostlistUnsupported);
            }
            Err(error) => {
                let known = self
                    .probe_known(&options, &seed, &BTreeSet::new(), true)
                    .await;
                self.apply_failure(&options, false, &error.to_string(), known);
                return Err(error);
            }
        };

        let list = match parse_node_list(&body) {
            Ok(list) => list,
            Err(error) => {
                let known = self
                    .probe_known(&options, &seed, &BTreeSet::new(), true)
                    .await;
                self.apply_failure(&options, false, &format!("hostlist decode: {error}"), known);
                return Err(error);
            }
        };

        if let Some(expected) = &options.network_id {
            if *expected != list.network_id {
                let error = ChainError::HostlistNetworkMismatch {
                    expected: expected.clone(),
                    actual: list.network_id.clone(),
                };
                let known = self
                    .probe_known(&options, &seed, &BTreeSet::new(), true)
                    .await;
                self.apply_failure(&options, false, &error.to_string(), known);
                return Err(error);
            }
        }
        let expected_network = options
            .network_id
            .clone()
            .unwrap_or_else(|| list.network_id.clone());
        let generated_age_ms = now_millis().map(|now| now.saturating_sub(list.generated_at));
        if let Some(age) = generated_age_ms {
            if age > MAX_HOSTLIST_AGE_MS {
                let reason = format!("hostlist is stale ({age} ms old)");
                let known = self
                    .probe_known(&options, &seed, &BTreeSet::new(), true)
                    .await;
                self.apply_failure(&options, false, &reason, known);
                return Err(ChainError::NoEligibleNode { reason });
            }
        }

        let (entries, mut rejected) = filter_node_list(&list, &options, &seed);
        let had_entries = !list.nodes.is_empty();
        let entries: Vec<_> = entries
            .into_iter()
            .take(options.max_verified_nodes)
            .collect();

        let client = self;
        let probes = entries.into_iter().map(|entry| {
            let options = options.clone();
            let expected_network = expected_network.clone();
            async move {
                match client
                    .status_on(&entry.http_url, Some(options.probe_timeout))
                    .await
                {
                    Ok(status) => verify_node(&entry, &status, &options, &expected_network)
                        .map_err(|reason| RejectedEntry {
                            url: entry.http_url.clone(),
                            reason,
                        }),
                    Err(error) => Err(RejectedEntry {
                        url: entry.http_url.clone(),
                        reason: error.to_string(),
                    }),
                }
            }
        });
        let results: Vec<Result<NodeEndpoint, RejectedEntry>> =
            stream::iter(probes).buffer_unordered(8).collect().await;
        let mut verified = Vec::new();
        for result in results {
            match result {
                Ok(endpoint) => verified.push(endpoint),
                Err(rejection) => rejected.push(rejection),
            }
        }

        let verified_any = !verified.is_empty();
        let verified_bases: BTreeSet<String> = verified.iter().map(|e| e.base.clone()).collect();
        // Known endpoints get the same live status treatment, so the cost/speed ranking
        // works even when the seed publishes no hostlist.
        let known = self
            .probe_known(&options, &seed, &verified_bases, !verified_any)
            .await;
        let mut endpoints = verified;
        endpoints.extend(known);
        endpoints = dedupe_endpoints(endpoints);

        if !verified_any {
            let error = if !had_entries {
                ChainError::NoEligibleNode {
                    reason: "the hostlist is empty".into(),
                }
            } else if rejected.is_empty() {
                ChainError::NoEligibleNode {
                    reason: "no hostlist entry verified".into(),
                }
            } else {
                ChainError::HostlistShardMismatch {
                    expected: options.shard_id.clone(),
                }
            };
            self.apply_failure(&options, false, &error.to_string(), endpoints.clone());
            return Err(error);
        }

        let report = DiscoveryReport {
            unsupported: false,
            fallback_to_seed: false,
            network_id: Some(list.network_id),
            primary_shard: Some(list.primary_shard),
            generated_at: Some(list.generated_at),
            generated_age_ms,
            endpoints: endpoints.clone(),
            rejected,
            error: None,
        };
        {
            let mut state = self.lock();
            state.endpoints = endpoints;
            state.fetched_at = Some(Instant::now());
            state.negative_until = None;
            state.unsupported = false;
            state.report = Some(report.clone());
        }
        Ok(report)
    }

    /// Apply a failed cycle. A previous good hostlist snapshot is kept on a transient
    /// failure; a 404 clears it, because the node has stopped publishing one.
    fn apply_failure(
        &self,
        options: &PoolOptions,
        unsupported: bool,
        reason: &str,
        known: Vec<NodeEndpoint>,
    ) -> DiscoveryReport {
        let mut state = self.lock();
        let keeps_hostlist = !unsupported
            && state
                .endpoints
                .iter()
                .any(|e| e.source == EndpointSource::Hostlist);
        if keeps_hostlist {
            // Keep the last hostlist snapshot but refresh the known endpoints' live facts.
            let mut merged = state.endpoints.clone();
            for endpoint in known {
                match merged.iter_mut().find(|e| e.base == endpoint.base) {
                    Some(existing) => *existing = endpoint,
                    None => merged.push(endpoint),
                }
            }
            state.endpoints = dedupe_endpoints(merged);
        } else {
            state.endpoints = dedupe_endpoints(known);
        }
        state.fetched_at = None;
        state.negative_until = Some(Instant::now() + options.negative_ttl);
        state.unsupported = unsupported;
        let report = DiscoveryReport {
            unsupported,
            fallback_to_seed: true,
            network_id: state
                .report
                .as_ref()
                .and_then(|report| report.network_id.clone()),
            primary_shard: state
                .report
                .as_ref()
                .and_then(|report| report.primary_shard.clone()),
            generated_at: state.report.as_ref().and_then(|report| report.generated_at),
            generated_age_ms: state
                .report
                .as_ref()
                .and_then(|report| report.generated_age_ms),
            endpoints: state.endpoints.clone(),
            rejected: Vec::new(),
            error: Some(reason.to_string()),
        };
        state.report = Some(report.clone());
        report
    }

    /// Read routing: one pass over the snapshot, rotated per call, seed last.
    async fn read_request(
        &self,
        method: Method,
        path: &str,
        body: Option<String>,
    ) -> Result<String, ChainError> {
        self.ensure_ready().await;
        let mut candidates = {
            let state = self.lock();
            if state.endpoints.is_empty() {
                vec![NodeEndpoint::seed(&self.base)]
            } else {
                state.endpoints.clone()
            }
        };
        if !candidates.iter().any(|endpoint| endpoint.base == self.base) {
            candidates.push(NodeEndpoint::seed(&self.base));
        }
        let start = {
            let mut state = self.lock();
            let index = state.read_cursor % candidates.len();
            state.read_cursor = state.read_cursor.wrapping_add(1);
            index
        };
        candidates.rotate_left(start);

        let mut last = None;
        for endpoint in candidates {
            match self
                .request_on(&endpoint.base, method, path, body.clone(), None)
                .await
            {
                Ok(response) => return Ok(response),
                Err(error) if is_read_retryable(&error) => last = Some(error),
                Err(error) => return Err(error),
            }
        }
        Err(last.unwrap_or_else(|| ChainError::NoEligibleNode {
            reason: "no read endpoint".into(),
        }))
    }

    /// Choose the one node a new signed deploy will be sent to, and the anchor and price
    /// it must be signed at.
    pub async fn plan_write(&self, configured_phlo_price: i64) -> Result<WritePlan, ChainError> {
        self.ensure_ready().await;
        let (options, endpoints, start) = {
            let mut state = self.lock();
            let endpoints = if state.endpoints.is_empty() {
                vec![NodeEndpoint::seed(&self.base)]
            } else {
                state.endpoints.clone()
            };
            let index = state.write_cursor % endpoints.len().max(1);
            state.write_cursor = state.write_cursor.wrapping_add(1);
            (state.options.clone(), endpoints, index)
        };

        let candidates: Vec<_> = endpoints
            .into_iter()
            .filter(|endpoint| endpoint.proposer)
            .collect();
        let (candidates, _) = filter_stale_targets(&candidates, DEPLOY_LIFESPAN_BLOCKS);
        if candidates.is_empty() {
            return Err(ChainError::NoEligibleNode {
                reason: "no proposer inside the deploy lifespan".into(),
            });
        }
        // The anchor covers every surviving target so a relayed copy stays valid; the
        // price covers only the node that receives the deploy, so the cheapest target is
        // actually cheaper.
        let anchor_floor = compute_anchor(&candidates);

        // Cheapest accepting tier first, freshest first within it, rotating so concurrent
        // deploys spread without paying more. The rest stay as fallbacks.
        let ranked = rank_write_targets(&candidates);
        let tier = best_write_tier(&ranked);
        let offset = start % tier.len().max(1);
        let mut ordered = tier.to_vec();
        ordered.rotate_left(offset);
        ordered.extend(ranked[tier.len()..].iter().cloned());

        let mut last = String::from("no candidate answered");
        for candidate in ordered {
            let status = match self
                .status_on(&candidate.base, Some(options.probe_timeout))
                .await
            {
                Ok(status) => status,
                Err(error) => {
                    last = error.to_string();
                    continue;
                }
            };
            if !status.shard_id.is_empty() && status.shard_id != options.shard_id {
                last = format!("{} is on shard {}", candidate.base, status.shard_id);
                continue;
            }
            if let Some(expected) = &options.network_id {
                if !status.network_id.is_empty() && status.network_id != *expected {
                    last = format!("{} is on network {}", candidate.base, status.network_id);
                    continue;
                }
            }
            if status.proposer == Some(false) {
                last = format!("{} cannot propose", candidate.base);
                continue;
            }
            if status.latest_block_number < 0 {
                last = format!("{} has no block height", candidate.base);
                continue;
            }

            let anchor = anchor_floor
                .map(|floor| floor.min(status.latest_block_number))
                .unwrap_or(status.latest_block_number);
            let phlo_price = configured_phlo_price.max(status.min_phlo_price);
            return Ok(WritePlan {
                base: candidate.base.clone(),
                node_id: candidate.node_id.clone(),
                anchor,
                phlo_price,
                accepts_deploys: status.accepts_deploys.unwrap_or(candidate.accepts_deploys),
            });
        }
        Err(ChainError::NoEligibleNode { reason: last })
    }

    /// Bind a deploy id to the node that will receive it. The first binding wins, so a
    /// late retry of the same signed bytes can never move to another node.
    pub fn bind_write(&self, deploy_id: &str, base: &str) {
        let mut state = self.lock();
        state
            .bindings
            .entry(deploy_id.to_string())
            .or_insert_with(|| base.to_string());
    }

    /// The node a deploy id was bound to, if this process bound it.
    pub fn bound_base(&self, deploy_id: &str) -> Option<String> {
        self.lock().bindings.get(deploy_id).cloned()
    }

    /// The bound node, or the seed for a deploy this process did not plan.
    pub fn write_base_for(&self, deploy_id: &str) -> String {
        self.bound_base(deploy_id)
            .unwrap_or_else(|| self.base.clone())
    }

    /// `GET /api/v1/status` through the pool (read routing).
    pub async fn status(&self) -> Result<serde_json::Value, ChainError> {
        let body = self
            .read_request(Method::Get, "/api/v1/status", None)
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
    pub async fn deploy(&self, signed: &SignedDeploy) -> Result<String, ChainError> {
        let body = serde_json::to_string(&signed.request_body())?;
        self.deploy_body(&body, &signed.deploy_id, signed.data.term.len())
            .await?;
        Ok(signed.deploy_id.clone())
    }

    /// Submit an exact request body to a chosen node. Used by the plan/bind path, which
    /// must not re-submit the same signed bytes anywhere else.
    pub async fn deploy_body_on(
        &self,
        base: &str,
        body: &str,
        deploy_id: &str,
        term_len: usize,
    ) -> Result<(), ChainError> {
        let response = self
            .transport
            .send(HttpRequest {
                method: Method::Post,
                url: format!("{base}/api/v1/deploy"),
                body: Some(body.to_string()),
                timeout: None,
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

    /// Submit an exact request body to the deploy's bound node (the seed when unbound).
    pub async fn deploy_body(
        &self,
        body: &str,
        deploy_id: &str,
        term_len: usize,
    ) -> Result<(), ChainError> {
        let base = self.write_base_for(deploy_id);
        self.deploy_body_on(&base, body, deploy_id, term_len).await
    }

    /// `GET /api/v1/deploy-status/{signature}`.
    pub async fn deploy_status(&self, deploy_id: &str) -> Result<DeployStatus, ChainError> {
        let path = format!("/api/v1/deploy-status/{deploy_id}");
        if let Some(base) = self.bound_base(deploy_id) {
            match self.request_on(&base, Method::Get, &path, None, None).await {
                Ok(body) => return serde_json::from_str(&body).map_err(Into::into),
                Err(error) if is_read_retryable(&error) => {}
                Err(error) => return Err(error),
            }
        }
        let body = self.read_request(Method::Get, &path, None).await?;
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
            .read_request(
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
    /// This does not bind `deployerId`, and `rho:block:data` reports height 0 there.
    pub async fn explore(&self, term: &str) -> Result<ExploreResponse, ChainError> {
        let body = serde_json::to_string(term)?;
        let response = self
            .read_request(Method::Post, "/api/v1/explore-deploy", Some(body))
            .await?;
        serde_json::from_str(&response).map_err(Into::into)
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
            .read_request(
                Method::Post,
                "/api/v1/explore-deploy-by-block-hash",
                Some(body),
            )
            .await?;
        serde_json::from_str(&response).map_err(Into::into)
    }

    /// `POST /api/v1/faucet` with a REV address. Always the seed: the faucet has its own
    /// per-node ledger and is not a signed deploy.
    pub async fn faucet(&self, address: &str) -> Result<serde_json::Value, ChainError> {
        let body = serde_json::to_string(&serde_json::json!({ "address": address }))?;
        let response = self
            .seed_request(Method::Post, "/api/v1/faucet", Some(body), None)
            .await?;
        serde_json::from_str(&response).map_err(Into::into)
    }

    /// `GET /api/last-finalized-block`.
    pub async fn last_finalized_block(&self) -> Result<BlockInfo, ChainError> {
        let body = self
            .read_request(Method::Get, "/api/last-finalized-block", None)
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
            .read_request(Method::Get, &format!("/api/v1/block/{hash}"), None)
            .await?;
        serde_json::from_str(&body).map_err(Into::into)
    }
}

fn fallback_endpoints(options: &PoolOptions, seed: &str) -> Vec<NodeEndpoint> {
    let mut endpoints = explicit_endpoints(options);
    endpoints.push(NodeEndpoint::seed(seed));
    dedupe_endpoints(endpoints)
}

#[cfg(not(target_arch = "wasm32"))]
fn now_millis() -> Option<i64> {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .ok()
        .map(|duration| duration.as_millis() as i64)
}

#[cfg(target_arch = "wasm32")]
fn now_millis() -> Option<i64> {
    None
}

async fn sleep(duration: Duration) {
    #[cfg(target_arch = "wasm32")]
    gloo_timers::future::TimeoutFuture::new(duration.as_millis() as u32).await;
    #[cfg(not(target_arch = "wasm32"))]
    tokio::time::sleep(duration).await;
}

#[cfg(test)]
mod pool_tests {
    use super::*;
    use async_trait::async_trait;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Mutex as StdMutex;
    use transport::{HttpRequest, HttpResponse, Transport};

    type Log = Arc<StdMutex<Vec<String>>>;
    type Handler = Box<dyn Fn(&HttpRequest) -> Result<HttpResponse, ChainError> + Send + Sync>;

    struct Scripted {
        log: Log,
        handler: Handler,
    }

    #[async_trait(?Send)]
    impl Transport for Scripted {
        async fn send(&self, request: HttpRequest) -> Result<HttpResponse, ChainError> {
            self.log
                .lock()
                .unwrap()
                .push(format!("{:?} {}", request.method, request.url));
            (self.handler)(&request)
        }
    }

    fn response(status: u16, body: impl Into<String>) -> HttpResponse {
        HttpResponse {
            status,
            body: body.into(),
            retry_after: None,
        }
    }

    fn status_body(address: &str, tip: i64, min_phlo_price: i64, accepts: bool) -> String {
        serde_json::json!({
            "address": address,
            "networkId": "testnet",
            "shardId": "/root",
            "latestBlockNumber": tip,
            "minPhloPrice": min_phlo_price,
            "proposer": true,
            "acceptsDeploys": accepts,
        })
        .to_string()
    }

    fn hostlist_body(entries: &[(&str, &str)]) -> String {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_millis() as i64;
        let nodes: Vec<_> = entries
            .iter()
            .map(|(node_id, url)| {
                serde_json::json!({
                    "nodeId": node_id,
                    "httpUrl": url,
                    "networkId": "testnet",
                    "shardId": "/root",
                    "nodeVersion": "0.1.0",
                    "latestBlockNumber": 100,
                    "proposer": true,
                    "acceptsDeploys": true,
                    "self": false,
                })
            })
            .collect();
        serde_json::json!({
            "networkId": "testnet",
            "primaryShard": "/root",
            "generatedAt": now,
            "ownLatestBlockNumber": 100,
            "nodes": nodes,
        })
        .to_string()
    }

    fn options() -> PoolOptions {
        PoolOptions {
            shard_id: "/root".into(),
            network_id: Some("testnet".into()),
            ..PoolOptions::default()
        }
    }

    fn client(
        handler: impl Fn(&HttpRequest) -> Result<HttpResponse, ChainError> + Send + Sync + 'static,
    ) -> (NodeClient, Log) {
        let log: Log = Arc::new(StdMutex::new(Vec::new()));
        let transport = Arc::new(Scripted {
            log: log.clone(),
            handler: Box::new(handler),
        });
        let client = NodeClient::with_options("http://seed:40403", transport, options()).unwrap();
        (client, log)
    }

    fn log_entries(log: &Log) -> Vec<String> {
        log.lock().unwrap().clone()
    }

    fn clear(log: &Log) {
        log.lock().unwrap().clear();
    }

    #[tokio::test]
    async fn a_404_hostlist_leaves_the_seed_alone() {
        let (client, log) = client(|request| {
            if request.url.ends_with("/api/v1/nodes") {
                Ok(response(404, "not found"))
            } else if request.url.ends_with("/api/v1/status") {
                Ok(response(200, status_body("seed", 100, 1, true)))
            } else {
                Ok(response(200, "deployed"))
            }
        });

        let plan = client.plan_write(1).await.unwrap();
        assert_eq!(plan.base, "http://seed:40403");
        assert_eq!(plan.anchor, 100);
        client
            .deploy_body_on(&plan.base, "{}", "id", 1)
            .await
            .unwrap();

        let entries = log_entries(&log);
        assert!(entries
            .iter()
            .all(|entry| entry.contains("http://seed:40403")));
        assert_eq!(
            entries
                .iter()
                .filter(|entry| entry.contains("Post"))
                .count(),
            1
        );
        assert!(matches!(
            client.discover().await,
            Err(ChainError::HostlistUnsupported)
        ));
    }

    #[tokio::test]
    async fn discovery_verifies_entries_and_plans_the_lowest_anchor() {
        let (client, log) = client(|request| {
            if request.url == "http://seed:40403/api/v1/nodes" {
                Ok(response(
                    200,
                    hostlist_body(&[("aa", "http://a:40403"), ("bb", "http://b:40403")]),
                ))
            } else if request.url == "http://a:40403/api/v1/status" {
                Ok(response(200, status_body("aa", 100, 1, true)))
            } else if request.url == "http://b:40403/api/v1/status" {
                Ok(response(200, status_body("bb", 99, 5, true)))
            } else {
                Ok(response(200, "deployed"))
            }
        });

        let plan = client.plan_write(1).await.unwrap();
        assert_eq!(plan.base, "http://a:40403");
        assert_eq!(plan.anchor, 99);
        assert_eq!(plan.phlo_price, 1);
        assert_eq!(client.nodes().len(), 2);

        clear(&log);
        let first = client.latest_block_number().await.unwrap();
        let second = client.latest_block_number().await.unwrap();
        assert_eq!(first, 100);
        assert_eq!(second, 99);
        let entries = log_entries(&log);
        assert!(entries[0].contains("http://a:40403/api/v1/status"));
        assert!(entries[1].contains("http://b:40403/api/v1/status"));
    }

    #[tokio::test]
    async fn a_write_refusal_is_not_retried_on_another_node() {
        let (client, log) = client(|request| {
            if request.url == "http://seed:40403/api/v1/nodes" {
                Ok(response(
                    200,
                    hostlist_body(&[("aa", "http://a:40403"), ("bb", "http://b:40403")]),
                ))
            } else if request.url.ends_with("/api/v1/status") {
                let (address, tip) = if request.url.starts_with("http://a:") {
                    ("aa", 100)
                } else {
                    ("bb", 99)
                };
                Ok(response(200, status_body(address, tip, 1, true)))
            } else {
                Ok(response(429, "too many"))
            }
        });

        let plan = client.plan_write(1).await.unwrap();
        clear(&log);
        let error = client
            .deploy_body_on(&plan.base, "{}", "id", 1)
            .await
            .unwrap_err();
        assert!(matches!(error, ChainError::RateLimited { .. }));
        let entries = log_entries(&log);
        assert_eq!(entries.len(), 1);
        assert!(entries[0].starts_with("Post http://a:40403/api/v1/deploy"));
    }

    #[tokio::test]
    async fn reads_fail_over_but_the_cursor_moves() {
        let fail_a = Arc::new(AtomicBool::new(false));
        let fail = fail_a.clone();
        let (client, log) = client(move |request| {
            if request.url == "http://seed:40403/api/v1/nodes" {
                Ok(response(
                    200,
                    hostlist_body(&[("aa", "http://a:40403"), ("bb", "http://b:40403")]),
                ))
            } else if request.url == "http://a:40403/api/v1/status" {
                if fail.load(Ordering::SeqCst) {
                    Ok(response(503, "throttled"))
                } else {
                    Ok(response(200, status_body("aa", 100, 1, true)))
                }
            } else if request.url == "http://b:40403/api/v1/status" {
                Ok(response(200, status_body("bb", 99, 1, true)))
            } else {
                Ok(response(200, "deployed"))
            }
        });

        // Prime discovery while both are healthy, then fail the first read target.
        assert!(client.discover().await.is_ok());
        fail_a.store(true, Ordering::SeqCst);
        clear(&log);
        let tip = client.latest_block_number().await.unwrap();
        assert_eq!(tip, 99);
        let entries = log_entries(&log);
        assert_eq!(entries.len(), 2);
        assert!(entries[0].contains("http://a:40403"));
        assert!(entries[1].contains("http://b:40403"));
    }

    #[tokio::test]
    async fn known_endpoints_are_probed_and_ranked_without_a_hostlist() {
        let options = PoolOptions {
            shard_id: "/root".into(),
            network_id: Some("testnet".into()),
            explicit_nodes: vec!["http://a:40403".into(), "http://b:40403".into()],
            ..PoolOptions::default()
        };
        let log: Log = Arc::new(StdMutex::new(Vec::new()));
        let transport = Arc::new(Scripted {
            log: log.clone(),
            handler: Box::new(|request| {
                if request.url.ends_with("/api/v1/nodes") {
                    Ok(response(404, "not found"))
                } else if request.url == "http://a:40403/api/v1/status" {
                    Ok(response(200, status_body("aa", 100, 1, true)))
                } else if request.url == "http://b:40403/api/v1/status" {
                    Ok(response(200, status_body("bb", 100, 5, true)))
                } else {
                    Ok(response(200, "deployed"))
                }
            }),
        });
        let client = NodeClient::with_options("http://seed:40403", transport, options).unwrap();
        let plan = client.plan_write(1).await.unwrap();
        assert_eq!(plan.base, "http://a:40403");
        assert_eq!(plan.anchor, 100);
        assert_eq!(plan.phlo_price, 1);
        assert_eq!(client.nodes().len(), 3);
    }

    #[tokio::test]
    async fn a_network_mismatch_is_a_typed_discovery_error() {
        let (client, _) = client(|request| {
            if request.url.ends_with("/api/v1/nodes") {
                let mut list: serde_json::Value =
                    serde_json::from_str(&hostlist_body(&[])).unwrap();
                list["networkId"] = serde_json::json!("devnet");
                Ok(response(200, list.to_string()))
            } else {
                Ok(response(200, status_body("seed", 1, 1, true)))
            }
        });
        assert!(matches!(
            client.discover().await,
            Err(ChainError::HostlistNetworkMismatch { .. })
        ));
    }
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
