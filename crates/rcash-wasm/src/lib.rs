//! WASM facade for the browser.
//!
//! R0a proves the target builds and that signing in wasm32 produces exactly the bytes
//! the native client produces. R3a adds the wallet, encrypted keystore and the SDK
//! operations.

use rcash_chain::deploy::DeployOptions;
use rcash_chain::KeyPair;
use wasm_bindgen::prelude::*;

/// The crate version, exported so the web app can assert it loaded the expected module.
#[wasm_bindgen]
pub fn version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

/// The pinned node revision the client was built against.
#[wasm_bindgen]
pub fn node_commit() -> String {
    "e2d073dcd02f1e560ccb84749937138a1e184b0b".to_string()
}

/// Sign the R0a parity fixture and return `{deployer, signature, deployId, address}`.
///
/// This exists to prove the wasm build signs identically to native; it is not the wallet
/// API (the secret never leaves the module in the real wallet).
#[wasm_bindgen]
pub fn parity_sign(secret_hex: &str, term: &str) -> Result<String, JsValue> {
    let key =
        KeyPair::from_secret_hex(secret_hex).map_err(|e| JsValue::from_str(&e.to_string()))?;
    let data = DeployOptions::new(term)
        .timestamp(1_700_000_000_000)
        .phlo(1_000_000, 1)
        .valid_after_block_number(12_345)
        .shard_id("/root")
        .build()
        .map_err(|e| JsValue::from_str(&e.to_string()))?;
    let signed = key
        .sign_deploy(data)
        .map_err(|e| JsValue::from_str(&e.to_string()))?;
    let address = key
        .rev_address()
        .map_err(|e| JsValue::from_str(&e.to_string()))?;
    Ok(format!(
        r#"{{"deployer":"{}","signature":"{}","deployId":"{}","address":"{}"}}"#,
        signed.deployer_hex, signed.signature_hex, signed.deploy_id, address
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use wasm_bindgen_test::wasm_bindgen_test;

    /// The same fixture the native CLI emits (`rcash parity-fixture`) and the TypeScript
    /// script checks. Wasm must produce these bytes exactly.
    #[wasm_bindgen_test]
    fn wasm_signs_the_r0a_fixture_identically() {
        let result = parity_sign(&"01".repeat(32), "Nil").expect("sign");
        assert!(
            result.contains("3044022059126613d09aad982947545c814ee8f4bc44ced6441f70cd8d29840c2d90f78c02206b2e2b145457fd54329096b246e005b64bdaa76ffd94563ec00613bea38d6287"),
            "signature: {result}"
        );
        assert!(
            result.contains("1111pjC8LgoBQApxaJeuGBJWhC4rAQDbVbkSMLaXjGdfiUynCXef9"),
            "address: {result}"
        );
    }
}
