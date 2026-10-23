//! The canonical strings are hashed with the node's BLAKE2b-256, so the hash the
//! contracts verify is the hash the Python and Rust tooling publishes.

use rchain_crypto::hash::blake2b256;
use rchain_shared::base16;

#[test]
fn python_vectors_hash_with_the_node_blake2b() {
    let vectors: serde_json::Value =
        serde_json::from_str(include_str!("../../../tests/terms/terms-vectors.json"))
            .expect("vectors");
    for key in ["zone", "feed", "pool", "book", "terms"] {
        let canonical = vectors[key]["canonical"].as_str().expect("canonical");
        let expected = vectors[key]["hash"].as_str().expect("hash");
        let actual = base16::encode(&blake2b256::hash(canonical.as_bytes()));
        assert_eq!(actual, expected, "{key} hash mismatch");
    }
}
