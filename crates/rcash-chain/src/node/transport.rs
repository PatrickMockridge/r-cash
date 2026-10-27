//! HTTP transport abstraction.
//!
//! The SDK is shared by the native CLI and the browser. Everything above this module
//! speaks `HttpRequest`/`HttpResponse`; only the transport differs.

use async_trait::async_trait;

use crate::error::ChainError;

/// HTTP method.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Method {
    Get,
    Post,
}

/// One HTTP request.
#[derive(Clone, Debug)]
pub struct HttpRequest {
    pub method: Method,
    pub url: String,
    /// JSON body, already serialized.
    pub body: Option<String>,
}

/// One HTTP response.
#[derive(Clone, Debug)]
pub struct HttpResponse {
    pub status: u16,
    pub body: String,
    /// `Retry-After` in seconds, when the node sent one.
    pub retry_after: Option<u64>,
}

/// A transport. `?Send` because the browser's fetch future is not `Send`.
#[async_trait(?Send)]
pub trait Transport {
    async fn send(&self, request: HttpRequest) -> Result<HttpResponse, ChainError>;
}

/// Native transport over `reqwest` (no TLS backend; devnet is HTTP).
#[cfg(not(target_arch = "wasm32"))]
pub struct NativeTransport {
    client: reqwest::Client,
}

#[cfg(not(target_arch = "wasm32"))]
impl NativeTransport {
    pub fn new() -> Result<Self, ChainError> {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .map_err(|e| ChainError::Transport(e.to_string()))?;
        Ok(Self { client })
    }
}

#[cfg(not(target_arch = "wasm32"))]
#[async_trait(?Send)]
impl Transport for NativeTransport {
    async fn send(&self, request: HttpRequest) -> Result<HttpResponse, ChainError> {
        let builder = match request.method {
            Method::Get => self.client.get(&request.url),
            Method::Post => self.client.post(&request.url),
        };
        let builder = match request.body {
            Some(body) => builder
                .header("content-type", "application/json")
                .body(body),
            None => builder,
        };
        let response = builder
            .send()
            .await
            .map_err(|e| ChainError::Transport(e.to_string()))?;
        let status = response.status().as_u16();
        let retry_after = response
            .headers()
            .get("retry-after")
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.trim().parse().ok());
        let body = response
            .text()
            .await
            .map_err(|e| ChainError::Transport(e.to_string()))?;
        Ok(HttpResponse {
            status,
            body,
            retry_after,
        })
    }
}

/// Browser transport over `fetch` (`gloo-net`).
#[cfg(target_arch = "wasm32")]
pub struct WasmTransport;

#[cfg(target_arch = "wasm32")]
#[async_trait(?Send)]
impl Transport for WasmTransport {
    async fn send(&self, request: HttpRequest) -> Result<HttpResponse, ChainError> {
        let builder = match request.method {
            Method::Get => gloo_net::http::Request::get(&request.url),
            Method::Post => gloo_net::http::Request::post(&request.url),
        };
        let response = match request.body {
            Some(body) => builder
                .header("content-type", "application/json")
                .body(body)
                .map_err(|e| ChainError::Transport(e.to_string()))?
                .send()
                .await
                .map_err(|e| ChainError::Transport(e.to_string()))?,
            None => builder
                .send()
                .await
                .map_err(|e| ChainError::Transport(e.to_string()))?,
        };
        let status = response.status();
        let retry_after = response
            .headers()
            .get("retry-after")
            .and_then(|value| value.trim().parse().ok());
        let body = response
            .text()
            .await
            .map_err(|e| ChainError::Transport(e.to_string()))?;
        Ok(HttpResponse {
            status,
            body,
            retry_after,
        })
    }
}
