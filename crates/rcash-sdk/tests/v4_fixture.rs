//! Offline SDK tests through the typed transport seam. No node is contacted.

use std::sync::Arc;

use async_trait::async_trait;
use rcash_chain::node::transport::{HttpRequest, HttpResponse, Transport};
use rcash_chain::node::NodeClient;
use rcash_chain::ChainError;
use rcash_core::manifest::V4Manifest;
use rcash_sdk::Client;
use serde_json::json;

struct Fixed(String);

#[async_trait(?Send)]
impl Transport for Fixed {
    async fn send(&self, _request: HttpRequest) -> Result<HttpResponse, ChainError> {
        Ok(HttpResponse {
            status: 200,
            body: self.0.clone(),
            retry_after: None,
        })
    }
}

fn manifest() -> V4Manifest {
    let uri = "rho:id:fixture";
    V4Manifest::from_json(
        &json!({
            "root_uri": uri, "clock_uri": uri, "verifier_uri": uri, "codec_uri": uri,
            "bounds_uri": uri, "admin_guard_uri": uri, "governor_uri": uri,
            "amm_math_uri": uri, "oracle_registry_uri": uri, "oracle_hub_uri": uri,
            "currency_registry_uri": uri, "stablecoin_directory_uri": uri,
            "asset_resolver_uri": uri, "transfer_book_uri": uri, "pool_template_uri": uri,
            "market_terms_uri": uri, "market_directory_uri": uri, "market_index_uri": uri,
            "market_factory_uri": uri, "tradability_gate_uri": uri,
            "listing_views_uri": uri, "account_factory_uri": uri
        })
        .to_string(),
    )
    .expect("fixture manifest")
}

fn client(body: serde_json::Value) -> Client {
    let node = NodeClient::with_transport("http://fixture", Arc::new(Fixed(body.to_string())))
        .expect("node");
    Client::with_node(node, None).with_v4_manifest(manifest())
}

fn explore(value: serde_json::Value) -> serde_json::Value {
    json!({
        "expr": [value],
        "block": {"blockHash": "00", "blockNumber": 1, "shardId": "/root", "timestamp": 0}
    })
}

fn stablecoin_entry() -> serde_json::Value {
    json!({"ExprMap": {"data": {
        "kind": {"ExprString": {"data": "stablecoin"}},
        "stablecoinUri": {"ExprString": {"data": "rho:id:sc"}},
        "custodyUri": {"ExprString": {"data": "rho:id:custody"}},
        "paramsUri": {"ExprString": {"data": "rho:id:params"}},
        "vaultUri": {"ExprString": {"data": "rho:id:vault"}},
        "liquidationUri": {"ExprString": {"data": "rho:id:liq"}},
        "savingsUri": {"ExprString": {"data": "rho:id:savings"}},
        "psmUri": {"ExprString": {"data": "rho:id:psm"}},
        "bufferUri": {"ExprString": {"data": "rho:id:buffer"}},
        "paramsHash": {"ExprString": {"data": "aa"}},
        "sponsor": {"ExprString": {"data": "bb"}},
        "status": {"ExprString": {"data": "active"}}
    }}})
}

fn external_entry() -> serde_json::Value {
    json!({"ExprMap": {"data": {
        "kind": {"ExprString": {"data": "external"}},
        "assetUri": {"ExprString": {"data": "rho:id:adapter"}},
        "decimals": {"ExprInt": {"data": 8}},
        "chain": {"ExprString": {"data": "test"}},
        "custodian": {"ExprString": {"data": "custodian"}},
        "sponsor": {"ExprString": {"data": "bb"}},
        "status": {"ExprString": {"data": "active"}}
    }}})
}

fn reply(values: serde_json::Value) -> serde_json::Value {
    json!({"ExprTuple": {"data": [{"ExprBool": {"data": true}}, values]}})
}

#[tokio::test]
async fn v4_currencies_parses_stablecoin_and_external_entries() {
    let body = explore(reply(json!({"ExprMap": {"data": {
        "USD": stablecoin_entry(),
        "USDC": external_entry()
    }}})));
    let entries = client(body).v4_currencies().await.expect("currencies");
    assert_eq!(entries.len(), 2);
    let usd = entries.iter().find(|entry| entry.code == "USD").unwrap();
    assert_eq!(usd.kind, "stablecoin");
    assert_eq!(usd.decimals, 8);
    let usdc = entries.iter().find(|entry| entry.code == "USDC").unwrap();
    assert_eq!(usdc.kind, "external");
    assert_eq!(usdc.asset_uri.as_deref(), Some("rho:id:adapter"));
    assert_eq!(usdc.vault_uri, "");
    assert_eq!(usdc.chain.as_deref(), Some("test"));
}

#[tokio::test]
async fn v4_currency_parses_an_external_entry() {
    let body = explore(reply(external_entry()));
    let entry = client(body).v4_currency("USDC").await.expect("currency");
    assert_eq!(entry.kind, "external");
    assert_eq!(entry.asset_uri.as_deref(), Some("rho:id:adapter"));
    assert_eq!(entry.vault_uri, "");
}

#[tokio::test]
async fn v4_market_accepts_the_reverse_orientation_record() {
    let market = json!({"ExprMap": {"data": {
        "marketId": {"ExprString": {"data": "USD/NGN:v1"}},
        "slug": {"ExprString": {"data": "usd-ngn-v1"}},
        "base": {"ExprString": {"data": "USD"}},
        "quote": {"ExprString": {"data": "NGN"}},
        "version": {"ExprInt": {"data": 1}},
        "termsHash": {"ExprString": {"data": "cc"}},
        "status": {"ExprString": {"data": "active"}}
    }}});
    let body = explore(reply(market));
    let record = client(body)
        .v4_market("NGN", "USD")
        .await
        .expect("market")
        .expect("some");
    assert_eq!(record.market_id, "USD/NGN:v1");
    assert_eq!(record.base, "USD");
    assert_eq!(record.quote, "NGN");
}

#[tokio::test]
async fn v4_price_in_is_identity_without_a_read() {
    let body = explore(reply(json!({"ExprInt": {"data": 0}})));
    let price = client(body).v4_price_in("USD", "USD").await.expect("price");
    assert_eq!(price, 100_000_000);
}
