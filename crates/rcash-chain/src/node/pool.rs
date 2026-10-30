//! The deploy hostlist and the endpoint pool (`GET /api/v1/nodes`, rholo Law 90).
//!
//! A node that publishes a hostlist answers with the live peers it has probed and found
//! deploy-capable. The list is advisory: a client re-verifies each entry against that
//! peer's `/api/v1/status` before relying on it, and still handles a 429 from a listed
//! node. When the endpoint is absent (404 on an older binary) the pool falls back to the
//! configured seed, so one client binary works on both networks.
//!
//! The routing rules are the node's own: reads may round-robin and fail over; a signed
//! deploy is sent to exactly one node and is never re-submitted elsewhere.

use std::collections::{BTreeMap, BTreeSet};
use std::time::Duration;

#[cfg(not(target_arch = "wasm32"))]
use std::time::Instant;
#[cfg(target_arch = "wasm32")]
use web_time::Instant;

use serde::{Deserialize, Serialize};

use crate::error::ChainError;

/// A deploy is expired once `height - validAfterBlockNumber >= DEPLOY_LIFESPAN` (rholo
/// `casper::multi_parent_casper::DEPLOY_LIFESPAN`).
pub const DEPLOY_LIFESPAN_BLOCKS: i64 = 50;

pub const DEFAULT_HOSTLIST_TTL: Duration = Duration::from_secs(30);
pub const DEFAULT_NEGATIVE_TTL: Duration = Duration::from_secs(60);
pub const DEFAULT_MAX_VERIFIED_NODES: usize = 16;
pub const DEFAULT_PROBE_TIMEOUT: Duration = Duration::from_secs(3);
/// A hostlist this old is not evidence of a live peer set.
pub const MAX_HOSTLIST_AGE_MS: i64 = 10 * 60 * 1000;

/// Whether `NodeClient` may ask its seed for a hostlist.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum DiscoveryMode {
    Enabled,
    Disabled,
}

/// Where an endpoint came from.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum EndpointSource {
    Seed,
    Explicit,
    Hostlist,
}

/// Pool configuration. `shard_id` is authoritative: entries for any other shard are dropped.
#[derive(Clone, Debug)]
pub struct PoolOptions {
    pub discovery: DiscoveryMode,
    pub shard_id: String,
    /// Expected network id. `None` adopts the one the seed's hostlist reports.
    pub network_id: Option<String>,
    /// Operator-supplied endpoints (`--nodes`), used alongside or instead of the hostlist.
    pub explicit_nodes: Vec<String>,
    pub hostlist_ttl: Duration,
    pub negative_ttl: Duration,
    pub max_verified_nodes: usize,
    pub probe_timeout: Duration,
}

impl Default for PoolOptions {
    fn default() -> Self {
        Self {
            discovery: DiscoveryMode::Enabled,
            shard_id: "/root".to_string(),
            network_id: None,
            explicit_nodes: Vec::new(),
            hostlist_ttl: DEFAULT_HOSTLIST_TTL,
            negative_ttl: DEFAULT_NEGATIVE_TTL,
            max_verified_nodes: DEFAULT_MAX_VERIFIED_NODES,
            probe_timeout: DEFAULT_PROBE_TIMEOUT,
        }
    }
}

/// One node the pool may use. `latest_block_number` is `-1` when it has not been observed.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NodeEndpoint {
    pub base: String,
    pub node_id: Option<String>,
    pub network_id: Option<String>,
    pub shard_id: Option<String>,
    pub latest_block_number: i64,
    pub min_phlo_price: i64,
    pub accepts_deploys: bool,
    pub proposer: bool,
    pub node_version: Option<String>,
    pub is_self: bool,
    pub source: EndpointSource,
}

impl NodeEndpoint {
    pub(crate) fn seed(base: &str) -> Self {
        Self {
            base: base.to_string(),
            node_id: None,
            network_id: None,
            shard_id: None,
            latest_block_number: -1,
            min_phlo_price: 0,
            accepts_deploys: true,
            proposer: true,
            node_version: None,
            is_self: false,
            source: EndpointSource::Seed,
        }
    }

    fn known_tip(&self) -> Option<i64> {
        (self.latest_block_number >= 0).then_some(self.latest_block_number)
    }
}

/// The node a signed deploy is bound to, and what it must be signed at.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WritePlan {
    pub base: String,
    pub node_id: Option<String>,
    /// `validAfterBlockNumber`: the lowest relevant tip, so relayed copies stay inside
    /// every peer's 50-block window.
    pub anchor: i64,
    pub phlo_price: i64,
    pub accepts_deploys: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RejectedEntry {
    pub url: String,
    pub reason: String,
}

/// The outcome of one discovery cycle, for `doctor` and `--json`.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiscoveryReport {
    pub unsupported: bool,
    pub fallback_to_seed: bool,
    pub network_id: Option<String>,
    pub primary_shard: Option<String>,
    pub generated_at: Option<i64>,
    pub generated_age_ms: Option<i64>,
    pub endpoints: Vec<NodeEndpoint>,
    pub rejected: Vec<RejectedEntry>,
    pub error: Option<String>,
}

/// The `GET /api/v1/nodes` body.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NodeListResponse {
    pub network_id: String,
    pub primary_shard: String,
    pub generated_at: i64,
    pub own_latest_block_number: i64,
    pub nodes: Vec<NodeListEntry>,
}

/// One advertised deploy-capable node.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NodeListEntry {
    /// The peer's TLS identity, hex. `/status.address` must name this.
    pub node_id: String,
    pub http_url: String,
    pub network_id: String,
    pub shard_id: String,
    #[serde(default)]
    pub node_version: String,
    #[serde(default)]
    pub latest_block_number: i64,
    #[serde(default)]
    pub proposer: bool,
    #[serde(default)]
    pub accepts_deploys: bool,
    #[serde(default, rename = "self")]
    pub is_self: bool,
}

/// The subset of `GET /api/v1/status` the pool verifies and ranks by.
#[derive(Clone, Debug, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NodeStatusView {
    #[serde(default)]
    pub address: String,
    #[serde(default)]
    pub network_id: String,
    #[serde(default)]
    pub shard_id: String,
    #[serde(default)]
    pub min_phlo_price: i64,
    #[serde(default)]
    pub latest_block_number: i64,
    #[serde(default)]
    pub proposer: Option<bool>,
    #[serde(default)]
    pub accepts_deploys: Option<bool>,
}

/// Mutable pool state. Guarded by a `std::sync::Mutex`; never held across an `await`.
pub(crate) struct PoolState {
    pub options: PoolOptions,
    pub endpoints: Vec<NodeEndpoint>,
    pub read_cursor: usize,
    pub write_cursor: usize,
    pub bindings: BTreeMap<String, String>,
    pub fetched_at: Option<Instant>,
    pub negative_until: Option<Instant>,
    pub unsupported: bool,
    pub refreshing: bool,
    pub report: Option<DiscoveryReport>,
}

impl PoolState {
    pub fn new(options: PoolOptions, seed: &str) -> Self {
        let mut endpoints = explicit_endpoints(&options);
        if !endpoints.iter().any(|e| e.base == seed) {
            endpoints.push(NodeEndpoint::seed(seed));
        }
        Self {
            options,
            endpoints,
            read_cursor: 0,
            write_cursor: 0,
            bindings: BTreeMap::new(),
            fetched_at: None,
            negative_until: None,
            unsupported: false,
            refreshing: false,
            report: None,
        }
    }

    pub fn fresh(&self) -> bool {
        self.fetched_at
            .map(|at| at.elapsed() < self.options.hostlist_ttl)
            .unwrap_or(false)
            || self
                .negative_until
                .map(|until| Instant::now() < until)
                .unwrap_or(false)
    }
}

pub(crate) fn explicit_endpoints(options: &PoolOptions) -> Vec<NodeEndpoint> {
    let mut out = Vec::new();
    let mut seen = BTreeSet::new();
    for raw in &options.explicit_nodes {
        let Some(base) = normalize_base(raw) else {
            continue;
        };
        if seen.insert(base.clone()) {
            out.push(NodeEndpoint {
                source: EndpointSource::Explicit,
                ..NodeEndpoint::seed(&base)
            });
        }
    }
    out
}

/// Trim and validate a base URL. Only `http(s)://host[:port][/path]` shapes; no userinfo.
pub fn normalize_base(raw: &str) -> Option<String> {
    let trimmed = raw.trim().trim_end_matches('/');
    if trimmed.is_empty()
        || trimmed.contains('@')
        || trimmed.chars().any(char::is_whitespace)
        || trimmed.contains('?')
        || trimmed.contains('#')
    {
        return None;
    }
    let lower = trimmed.to_ascii_lowercase();
    let rest = lower
        .strip_prefix("http://")
        .or_else(|| lower.strip_prefix("https://"))?;
    if rest.is_empty() || rest.starts_with('/') {
        return None;
    }
    Some(trimmed.to_string())
}

/// A native client has no TLS backend and a browser cannot fetch HTTP from an HTTPS page.
/// The seed's scheme decides which entries are usable.
pub fn scheme_allowed(url: &str, seed: &str) -> bool {
    let url = url.to_ascii_lowercase();
    if seed
        .trim_start()
        .to_ascii_lowercase()
        .starts_with("https://")
    {
        url.starts_with("https://")
    } else {
        url.starts_with("http://")
    }
}

pub fn parse_node_list(body: &str) -> Result<NodeListResponse, ChainError> {
    serde_json::from_str(body).map_err(Into::into)
}

/// Keep entries for this network and shard that claim to propose, dedupe them, and rank
/// accepting nodes first. Malformed or out-of-scope entries are reported, not served.
pub fn filter_node_list(
    list: &NodeListResponse,
    options: &PoolOptions,
    seed: &str,
) -> (Vec<NodeListEntry>, Vec<RejectedEntry>) {
    let expected_network = options.network_id.as_deref().unwrap_or(&list.network_id);
    let mut accepted = Vec::new();
    let mut rejected = Vec::new();
    let mut seen_urls = BTreeSet::new();
    let mut seen_ids = BTreeSet::new();

    for entry in &list.nodes {
        let reject = |reason: &str| RejectedEntry {
            url: entry.http_url.clone(),
            reason: reason.to_string(),
        };
        if entry.network_id != expected_network {
            rejected.push(reject("network mismatch"));
            continue;
        }
        if entry.shard_id != options.shard_id {
            rejected.push(reject("shard mismatch"));
            continue;
        }
        if !entry.proposer {
            rejected.push(reject("not a proposer"));
            continue;
        }
        let Some(base) = normalize_base(&entry.http_url) else {
            rejected.push(reject("malformed URL"));
            continue;
        };
        if !scheme_allowed(&base, seed) {
            rejected.push(reject("scheme not usable by this client"));
            continue;
        }
        if !seen_urls.insert(base.clone()) || !seen_ids.insert(entry.node_id.clone()) {
            rejected.push(reject("duplicate entry"));
            continue;
        }
        let mut normalized = entry.clone();
        normalized.http_url = base;
        accepted.push(normalized);
    }

    accepted.sort_by(|a, b| {
        b.accepts_deploys
            .cmp(&a.accepts_deploys)
            .then(b.latest_block_number.cmp(&a.latest_block_number))
            .then(a.node_id.cmp(&b.node_id))
    });
    (accepted, rejected)
}

/// `/status.address` must name the advertised node id (TLS identity). Older nodes answer
/// with the `rnode://` form; tolerate it, exactly as the node's own probe does.
pub fn address_names_peer(address: &str, node_id: &str) -> bool {
    address == node_id || address.starts_with(&format!("rnode://{node_id}@"))
}

/// Turn a hostlist entry and its live status into a pool endpoint.
pub fn verify_node(
    entry: &NodeListEntry,
    status: &NodeStatusView,
    options: &PoolOptions,
    expected_network: &str,
) -> Result<NodeEndpoint, String> {
    if !status.network_id.is_empty() && status.network_id != expected_network {
        return Err("status network mismatch".into());
    }
    if !status.shard_id.is_empty() && status.shard_id != options.shard_id {
        return Err("status shard mismatch".into());
    }
    if status.proposer == Some(false) {
        return Err("status says not a proposer".into());
    }
    if !status.address.is_empty() && !address_names_peer(&status.address, &entry.node_id) {
        return Err("status address does not name the advertised node".into());
    }
    if status.latest_block_number < 0 {
        return Err("status has no block height".into());
    }
    Ok(NodeEndpoint {
        base: entry.http_url.clone(),
        node_id: Some(entry.node_id.clone()),
        network_id: Some(status.network_id.clone()),
        shard_id: Some(status.shard_id.clone()),
        latest_block_number: status.latest_block_number,
        min_phlo_price: status.min_phlo_price,
        accepts_deploys: status.accepts_deploys.unwrap_or(entry.accepts_deploys),
        proposer: true,
        node_version: if entry.node_version.is_empty() {
            None
        } else {
            Some(entry.node_version.clone())
        },
        is_self: entry.is_self,
        source: EndpointSource::Hostlist,
    })
}

/// Deduplicate by base URL and node id, first deterministic entry wins.
pub fn dedupe_endpoints(endpoints: Vec<NodeEndpoint>) -> Vec<NodeEndpoint> {
    let mut seen_urls = BTreeSet::new();
    let mut seen_ids = BTreeSet::new();
    let mut out = Vec::with_capacity(endpoints.len());
    for endpoint in endpoints {
        if !seen_urls.insert(endpoint.base.clone()) {
            continue;
        }
        if let Some(id) = &endpoint.node_id {
            if !seen_ids.insert(id.clone()) {
                continue;
            }
        }
        out.push(endpoint);
    }
    out
}

/// A read may try the next node after these failures. A write never does.
pub fn is_read_retryable(error: &ChainError) -> bool {
    match error {
        ChainError::Transport(_)
        | ChainError::RateLimited { .. }
        | ChainError::Unavailable { .. }
        | ChainError::Decode(_) => true,
        ChainError::Http { status, .. } => *status >= 500,
        _ => false,
    }
}

/// Drop cached targets at least one deploy lifespan behind the freshest cached tip. An
/// endpoint with no observed tip is kept: `plan_write` probes it live before signing.
pub fn filter_stale_targets(
    endpoints: &[NodeEndpoint],
    lifespan: i64,
) -> (Vec<NodeEndpoint>, Vec<RejectedEntry>) {
    let Some(max) = endpoints.iter().filter_map(NodeEndpoint::known_tip).max() else {
        return (endpoints.to_vec(), Vec::new());
    };
    let mut kept = Vec::with_capacity(endpoints.len());
    let mut rejected = Vec::new();
    for endpoint in endpoints {
        match endpoint.known_tip() {
            Some(tip) if max - tip >= lifespan => rejected.push(RejectedEntry {
                url: endpoint.base.clone(),
                reason: format!("{} blocks behind the freshest target", max - tip),
            }),
            _ => kept.push(endpoint.clone()),
        }
    }
    (kept, rejected)
}

/// Rank write targets for cost and speed: a node that is accepting work first, then the
/// lowest fee floor, then the freshest tip. The order is deterministic for equal rows.
pub fn rank_write_targets(endpoints: &[NodeEndpoint]) -> Vec<NodeEndpoint> {
    let mut ranked = endpoints.to_vec();
    ranked.sort_by(|a, b| {
        b.accepts_deploys
            .cmp(&a.accepts_deploys)
            .then(a.min_phlo_price.cmp(&b.min_phlo_price))
            .then(b.latest_block_number.cmp(&a.latest_block_number))
            .then(a.node_id.cmp(&b.node_id))
            .then(a.base.cmp(&b.base))
    });
    ranked
}

/// The slice sharing the best `(accepts_deploys, min_phlo_price)` pair. Round-robin stays
/// inside it so spreading load never costs more.
pub fn best_write_tier(ranked: &[NodeEndpoint]) -> &[NodeEndpoint] {
    let Some(first) = ranked.first() else {
        return &[];
    };
    let len = ranked
        .iter()
        .take_while(|endpoint| {
            endpoint.accepts_deploys == first.accepts_deploys
                && endpoint.min_phlo_price == first.min_phlo_price
        })
        .count();
    &ranked[..len]
}

/// The lowest observed tip — the conservative `validAfterBlockNumber` anchor.
pub fn compute_anchor(endpoints: &[NodeEndpoint]) -> Option<i64> {
    endpoints.iter().filter_map(NodeEndpoint::known_tip).min()
}

/// The highest observed fee floor.
pub fn compute_phlo_floor(endpoints: &[NodeEndpoint]) -> i64 {
    endpoints
        .iter()
        .map(|endpoint| endpoint.min_phlo_price.max(0))
        .max()
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn options() -> PoolOptions {
        PoolOptions::default()
    }

    fn list() -> NodeListResponse {
        serde_json::from_str(
            r#"{
              "networkId": "testnet",
              "primaryShard": "/testnet",
              "generatedAt": 1761868800123,
              "ownLatestBlockNumber": 128,
              "nodes": [
                {"nodeId": "aa", "httpUrl": "http://10.0.0.1:40403", "networkId": "testnet",
                 "shardId": "/testnet", "nodeVersion": "0.1.0", "latestBlockNumber": 128,
                 "proposer": true, "acceptsDeploys": true, "self": true},
                {"nodeId": "bb", "httpUrl": "http://10.0.0.2:40403/", "networkId": "testnet",
                 "shardId": "/testnet", "nodeVersion": "0.1.0", "latestBlockNumber": 127,
                 "proposer": true, "acceptsDeploys": false, "self": false},
                {"nodeId": "cc", "httpUrl": "http://10.0.0.3:40403", "networkId": "testnet",
                 "shardId": "/root", "nodeVersion": "0.1.0", "latestBlockNumber": 127,
                 "proposer": true, "acceptsDeploys": true, "self": false},
                {"nodeId": "dd", "httpUrl": "http://10.0.0.4:40403", "networkId": "testnet",
                 "shardId": "/testnet", "nodeVersion": "0.1.0", "latestBlockNumber": 127,
                 "proposer": false, "acceptsDeploys": true, "self": false},
                {"nodeId": "aa", "httpUrl": "http://10.0.0.9:40403", "networkId": "testnet",
                 "shardId": "/testnet", "nodeVersion": "0.1.0", "latestBlockNumber": 1,
                 "proposer": true, "acceptsDeploys": true, "self": false}
              ]
            }"#,
        )
        .unwrap()
    }

    #[test]
    fn the_wire_shape_is_the_nodes_camel_case_envelope() {
        let parsed = parse_node_list(&serde_json::to_string(&list()).unwrap()).unwrap();
        assert_eq!(parsed.network_id, "testnet");
        assert_eq!(parsed.primary_shard, "/testnet");
        assert_eq!(parsed.nodes[0].node_id, "aa");
        assert!(parsed.nodes[0].is_self);
        assert!(parsed.nodes[0].accepts_deploys);
    }

    #[test]
    fn only_this_network_shard_and_proposers_are_served() {
        let mut opts = options();
        opts.shard_id = "/testnet".into();
        let (entries, rejected) = filter_node_list(&list(), &opts, "http://10.0.0.1:40403");
        let ids: Vec<_> = entries.iter().map(|e| e.node_id.as_str()).collect();
        assert_eq!(ids, vec!["aa", "bb"]);
        assert_eq!(rejected.len(), 3);
        assert!(rejected.iter().any(|r| r.reason == "shard mismatch"));
        assert!(rejected.iter().any(|r| r.reason == "not a proposer"));
        assert!(rejected.iter().any(|r| r.reason == "duplicate entry"));
        assert_eq!(entries[0].http_url, "http://10.0.0.1:40403");
        assert_eq!(entries[1].http_url, "http://10.0.0.2:40403");
    }

    #[test]
    fn a_network_mismatch_is_rejected() {
        let mut opts = options();
        opts.network_id = Some("devnet".into());
        let (entries, rejected) = filter_node_list(&list(), &opts, "http://10.0.0.1:40403");
        assert!(entries.is_empty());
        assert_eq!(rejected.len(), list().nodes.len());
    }

    #[test]
    fn the_scheme_rule_follows_the_seed() {
        assert!(scheme_allowed("http://a:40403", "http://seed:40403"));
        assert!(!scheme_allowed("https://a", "http://seed:40403"));
        assert!(scheme_allowed("https://a", "https://seed"));
        assert!(!scheme_allowed("http://a:40403", "https://seed"));
    }

    #[test]
    fn status_must_name_the_advertised_node() {
        let mut opts = options();
        opts.shard_id = "/testnet".into();
        let entry = list().nodes[0].clone();
        let status = NodeStatusView {
            address: "aa".into(),
            network_id: "testnet".into(),
            shard_id: "/testnet".into(),
            min_phlo_price: 2,
            latest_block_number: 130,
            proposer: Some(true),
            accepts_deploys: Some(true),
        };
        let endpoint = verify_node(&entry, &status, &opts, "testnet").unwrap();
        assert_eq!(endpoint.latest_block_number, 130);
        assert_eq!(endpoint.min_phlo_price, 2);
        assert_eq!(endpoint.source, EndpointSource::Hostlist);

        let mut wrong = status;
        wrong.address = "bb".into();
        assert!(verify_node(&entry, &wrong, &opts, "testnet").is_err());

        wrong.address = "rnode://aa@10.0.0.1?protocol=40400&discovery=40404".into();
        assert!(verify_node(&entry, &wrong, &opts, "testnet").is_ok());
    }

    #[test]
    fn stale_targets_and_the_anchor() {
        let endpoint = |base: &str, tip: i64| NodeEndpoint {
            latest_block_number: tip,
            ..NodeEndpoint::seed(base)
        };
        let endpoints = vec![
            endpoint("a", 100),
            endpoint("b", 51),
            endpoint("c", 50),
            endpoint("d", -1),
        ];
        let (kept, rejected) = filter_stale_targets(&endpoints, DEPLOY_LIFESPAN_BLOCKS);
        let bases: Vec<_> = kept.iter().map(|e| e.base.as_str()).collect();
        assert_eq!(bases, vec!["a", "b", "d"]);
        assert_eq!(rejected.len(), 1);
        assert_eq!(compute_anchor(&endpoints), Some(50));
    }

    #[test]
    fn write_targets_rank_accepting_cheap_and_fresh_first() {
        let endpoint = |base: &str, accepts: bool, price: i64, tip: i64| NodeEndpoint {
            accepts_deploys: accepts,
            min_phlo_price: price,
            latest_block_number: tip,
            ..NodeEndpoint::seed(base)
        };
        let endpoints = vec![
            endpoint("a", true, 5, 100),
            endpoint("b", true, 1, 90),
            endpoint("c", false, 0, 110),
            endpoint("d", true, 1, 95),
        ];
        let ranked = rank_write_targets(&endpoints);
        let bases: Vec<_> = ranked.iter().map(|e| e.base.as_str()).collect();
        assert_eq!(bases, vec!["d", "b", "a", "c"]);
        let tier: Vec<_> = best_write_tier(&ranked)
            .iter()
            .map(|e| e.base.as_str())
            .collect();
        assert_eq!(tier, vec!["d", "b"]);
    }

    #[test]
    fn the_phlo_floor_is_the_highest_observed_minimum() {
        let endpoints = vec![
            NodeEndpoint {
                min_phlo_price: 1,
                ..NodeEndpoint::seed("a")
            },
            NodeEndpoint {
                min_phlo_price: 7,
                ..NodeEndpoint::seed("b")
            },
        ];
        assert_eq!(compute_phlo_floor(&endpoints), 7);
    }

    #[test]
    fn malformed_urls_are_not_bases() {
        assert_eq!(
            normalize_base(" http://a:40403/ ").as_deref(),
            Some("http://a:40403")
        );
        assert!(normalize_base("http://u:p@a:40403").is_none());
        assert!(normalize_base("ftp://a").is_none());
        assert!(normalize_base("http://").is_none());
    }
}
