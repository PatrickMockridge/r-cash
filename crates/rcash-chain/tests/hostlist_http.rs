//! End-to-end discovery over a real local HTTP listener.
//!
//! The scripted-transport tests pin the routing decisions; this one proves the wire path:
//! `GET /api/v1/nodes`, the `/api/v1/status` re-verification, and the `nodeId` ↔ `address`
//! check through the native transport.

use std::io::{Read, Write};
use std::net::TcpListener;
use std::time::Duration;

use rcash_chain::node::pool::PoolOptions;
use rcash_chain::node::NodeClient;

fn serve(status: u16, body: &str) -> String {
    format!(
        "HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    )
}

#[tokio::test]
async fn discovery_and_status_work_over_http() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let hostlist = format!(
        r#"{{"networkId":"testnet","primaryShard":"/root","generatedAt":{},"ownLatestBlockNumber":7,
            "nodes":[{{"nodeId":"aa","httpUrl":"http://127.0.0.1:{port}","networkId":"testnet",
            "shardId":"/root","nodeVersion":"0.1.0","latestBlockNumber":7,
            "proposer":true,"acceptsDeploys":true,"self":true}}]}}"#,
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_millis()
    );
    let status = r#"{"address":"aa","networkId":"testnet","shardId":"/root",
        "latestBlockNumber":7,"minPhloPrice":2,"proposer":true,"acceptsDeploys":true}"#;

    std::thread::spawn(move || {
        for stream in listener.incoming().take(16) {
            let Ok(mut stream) = stream else { continue };
            let mut buffer = [0u8; 2048];
            let read = stream.read(&mut buffer).unwrap_or(0);
            let request = String::from_utf8_lossy(&buffer[..read]);
            let path = request
                .lines()
                .next()
                .and_then(|line| line.split_whitespace().nth(1))
                .unwrap_or("/");
            let response = match path {
                "/api/v1/nodes" => serve(200, &hostlist),
                "/api/v1/status" => serve(200, status),
                _ => serve(404, "{}"),
            };
            let _ = stream.write_all(response.as_bytes());
        }
    });

    let options = PoolOptions {
        shard_id: "/root".into(),
        network_id: Some("testnet".into()),
        probe_timeout: Duration::from_secs(3),
        ..PoolOptions::default()
    };
    let node = NodeClient::new_with_options(format!("http://127.0.0.1:{port}"), options).unwrap();
    let plan = node.plan_write(1).await.unwrap();
    assert_eq!(plan.base, format!("http://127.0.0.1:{port}"));
    assert_eq!(plan.anchor, 7);
    assert_eq!(plan.phlo_price, 2);
    assert_eq!(node.nodes().len(), 1);
}
