//! Hostlist routing through the SDK: the signed anchor/price come from the plan, and a
//! cached deploy never moves off its pinned node.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use rcash_chain::node::pool::PoolOptions;
use rcash_chain::node::transport::{HttpRequest, HttpResponse, Transport};
use rcash_chain::node::NodeClient;
use rcash_chain::{ChainError, KeyPair};
use rcash_sdk::Client;

type Log = Arc<Mutex<Vec<(String, String)>>>;
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
            .push((format!("{:?}", request.method), request.url.clone()));
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

fn now_millis() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_millis() as i64
}

fn hostlist_body() -> String {
    serde_json::json!({
        "networkId": "testnet",
        "primaryShard": "/root",
        "generatedAt": now_millis(),
        "ownLatestBlockNumber": 100,
        "nodes": [
            {"nodeId": "aa", "httpUrl": "http://a:40403", "networkId": "testnet",
             "shardId": "/root", "nodeVersion": "0.1.0", "latestBlockNumber": 100,
             "proposer": true, "acceptsDeploys": true, "self": false},
            {"nodeId": "bb", "httpUrl": "http://b:40403", "networkId": "testnet",
             "shardId": "/root", "nodeVersion": "0.1.0", "latestBlockNumber": 90,
             "proposer": true, "acceptsDeploys": true, "self": false}
        ]
    })
    .to_string()
}

fn status_body(address: &str, tip: i64, min_phlo_price: i64) -> String {
    serde_json::json!({
        "address": address,
        "networkId": "testnet",
        "shardId": "/root",
        "latestBlockNumber": tip,
        "minPhloPrice": min_phlo_price,
        "proposer": true,
        "acceptsDeploys": true,
    })
    .to_string()
}

fn processed_body() -> String {
    serde_json::json!({
        "ProcessedWithSuccess": {
            "deployResult": [],
            "block": {"blockHash": "beef", "blockNumber": 1, "shardId": "/root", "timestamp": 0}
        }
    })
    .to_string()
}

fn client(
    handler: impl Fn(&HttpRequest) -> Result<HttpResponse, ChainError> + Send + Sync + 'static,
) -> (Client, Log) {
    let log: Log = Arc::new(Mutex::new(Vec::new()));
    let transport = Arc::new(Scripted {
        log: log.clone(),
        handler: Box::new(handler),
    });
    let options = PoolOptions {
        shard_id: "/root".into(),
        network_id: Some("testnet".into()),
        ..PoolOptions::default()
    };
    let node = NodeClient::with_options("http://seed:40403", transport, options).unwrap();
    let key = KeyPair::from_secret_hex(&"01".repeat(32)).unwrap();
    (
        Client::with_node(node, Some(key))
            .with_shard("/root")
            .with_phlo(1_000_000, 1),
        log,
    )
}

fn post_urls(log: &Log) -> Vec<String> {
    log.lock()
        .unwrap()
        .iter()
        .filter(|(method, _)| method == "Post")
        .map(|(_, url)| url.clone())
        .collect()
}

#[tokio::test]
async fn a_deploy_is_signed_at_the_planned_anchor_and_price() {
    let bodies: Arc<Mutex<Vec<serde_json::Value>>> = Arc::new(Mutex::new(Vec::new()));
    let captured = bodies.clone();
    let (client, log) = client(move |request| {
        if request.url == "http://seed:40403/api/v1/nodes" {
            Ok(response(200, hostlist_body()))
        } else if request.url == "http://a:40403/api/v1/status" {
            Ok(response(200, status_body("aa", 100, 1)))
        } else if request.url == "http://b:40403/api/v1/status" {
            Ok(response(200, status_body("bb", 90, 7)))
        } else if request.url.ends_with("/api/v1/deploy") {
            captured
                .lock()
                .unwrap()
                .push(serde_json::from_str(request.body.as_deref().unwrap()).unwrap());
            Ok(response(200, "Deployed"))
        } else if request.url.contains("/deploy-status/") {
            Ok(response(200, processed_body()))
        } else if request.url.contains("/api/is-finalized/") {
            Ok(response(200, "true"))
        } else {
            panic!("unexpected URL {}", request.url)
        }
    });

    let outcome = client.deploy_term("Nil").await.unwrap();
    assert!(outcome.is_success());
    let bodies = bodies.lock().unwrap();
    assert_eq!(bodies.len(), 1);
    assert_eq!(bodies[0]["data"]["validAfterBlockNumber"], 90);
    assert_eq!(bodies[0]["data"]["phloPrice"], 1);
    assert_eq!(post_urls(&log), vec!["http://a:40403/api/v1/deploy"]);
}

#[tokio::test]
async fn distinct_deploys_rotate_across_nodes() {
    let (client, log) = client(move |request| {
        if request.url == "http://seed:40403/api/v1/nodes" {
            Ok(response(200, hostlist_body()))
        } else if request.url == "http://a:40403/api/v1/status" {
            Ok(response(200, status_body("aa", 100, 1)))
        } else if request.url == "http://b:40403/api/v1/status" {
            Ok(response(200, status_body("bb", 90, 1)))
        } else if request.url.ends_with("/api/v1/deploy") {
            Ok(response(200, "Deployed"))
        } else if request.url.contains("/deploy-status/") {
            Ok(response(200, processed_body()))
        } else if request.url.contains("/api/is-finalized/") {
            Ok(response(200, "true"))
        } else {
            panic!("unexpected URL {}", request.url)
        }
    });

    client.deploy_term("Nil").await.unwrap();
    client.deploy_term("Nil").await.unwrap();
    assert_eq!(
        post_urls(&log),
        vec![
            "http://a:40403/api/v1/deploy",
            "http://b:40403/api/v1/deploy"
        ]
    );
}

#[tokio::test]
async fn a_cached_retry_stays_on_its_pinned_node() {
    let posts = Arc::new(AtomicUsize::new(0));
    let counter = posts.clone();
    let (client, log) = client(move |request| {
        if request.url == "http://seed:40403/api/v1/nodes" {
            Ok(response(200, hostlist_body()))
        } else if request.url.ends_with("/api/v1/status") {
            if request.url.starts_with("http://a:") {
                Ok(response(200, status_body("aa", 100, 1)))
            } else {
                Ok(response(200, status_body("bb", 90, 1)))
            }
        } else if request.url.ends_with("/api/v1/deploy") {
            let attempt = counter.fetch_add(1, Ordering::SeqCst);
            if attempt == 0 {
                Ok(response(503, "throttled"))
            } else {
                Ok(response(200, "Deployed"))
            }
        } else if request.url.contains("/deploy-status/") {
            if counter.load(Ordering::SeqCst) >= 2 {
                Ok(response(200, processed_body()))
            } else {
                Ok(response(200, r#"{"NotProcessed":{"status":"pooled"}}"#))
            }
        } else if request.url.contains("/api/is-finalized/") {
            Ok(response(200, "true"))
        } else {
            panic!("unexpected URL {}", request.url)
        }
    });

    let dir = std::env::temp_dir().join(format!("rcash-hostlist-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();

    let first = client.deploy_term_cached("Nil", "pin", &dir).await;
    assert!(matches!(first, Err(ChainError::Unavailable { .. })));
    let second = client.deploy_term_cached("Nil", "pin", &dir).await.unwrap();
    assert!(second.is_success());

    let urls = post_urls(&log);
    assert_eq!(urls.len(), 2);
    assert!(urls.iter().all(|url| url.starts_with("http://a:40403/")));
    let cache = std::fs::read_to_string(dir.join("pin.json")).unwrap();
    assert!(cache.contains("\"node\":\"http://a:40403\""), "{cache}");
    let _ = std::fs::remove_dir_all(&dir);
}

#[tokio::test]
async fn a_legacy_cache_entry_goes_to_the_seed() {
    let posts = Arc::new(AtomicUsize::new(0));
    let counter = posts.clone();
    let (client, log) = client(move |request| {
        if request.url == "http://seed:40403/api/v1/deploy" {
            counter.fetch_add(1, Ordering::SeqCst);
            Ok(response(200, "Deployed"))
        } else if request.url.contains("/deploy-status/") {
            if counter.load(Ordering::SeqCst) >= 1 {
                Ok(response(200, processed_body()))
            } else {
                Ok(response(200, r#"{"NotProcessed":{"status":"pooled"}}"#))
            }
        } else if request.url.contains("/api/is-finalized/") {
            Ok(response(200, "true"))
        } else if request.url.ends_with("/api/v1/nodes") {
            Ok(response(404, "not found"))
        } else if request.url.ends_with("/api/v1/status") {
            Ok(response(200, status_body("seed", 100, 1)))
        } else {
            panic!("unexpected URL {}", request.url)
        }
    });

    let dir = std::env::temp_dir().join(format!("rcash-hostlist-legacy-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("legacy.json"),
        r#"{"term":"Nil","deploy_id":"deadbeef","body":"{}"}"#,
    )
    .unwrap();

    let outcome = client
        .deploy_term_cached("Nil", "legacy", &dir)
        .await
        .unwrap();
    assert!(outcome.is_success());
    assert_eq!(posts.load(Ordering::SeqCst), 1);
    assert_eq!(post_urls(&log), vec!["http://seed:40403/api/v1/deploy"]);
    let _ = std::fs::remove_dir_all(&dir);
}
