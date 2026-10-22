//! REV address derivation.
//!
//! Mirrors `rholang/src/util/rev_address.rs`: coin id `000000`, version `00`, then
//! `keccak256(eth address)` as the key hash, then a four-byte BLAKE2b-256 checksum,
//! base58-encoded. The R0a vector test pins it to the node's implementation.

use rchain_crypto::hash::{blake2b256, keccak256};
use rchain_shared::base16;

use crate::error::ChainError;

/// REV address prefix: `000000` (coin id) followed by `00` (version).
const PREFIX: [u8; 4] = [0, 0, 0, 0];
const CHECKSUM_LENGTH: usize = 4;
const ETH_ADDRESS_HEX_LENGTH: usize = 40;

/// Derive a REV address from a 65-byte uncompressed secp256k1 public key.
pub fn rev_address_from_public_key(public_key: &[u8]) -> Result<String, ChainError> {
    if public_key.len() != 65 || public_key[0] != 0x04 {
        return Err(ChainError::BadKey(format!(
            "expected a 65-byte uncompressed public key, got {} bytes",
            public_key.len()
        )));
    }
    let eth_hash = keccak256::hash(&public_key[1..]);
    let eth_hex = base16::encode(&eth_hash);
    let eth_address = &eth_hex[eth_hex.len() - ETH_ADDRESS_HEX_LENGTH..];
    rev_address_from_eth_address(eth_address)
}

/// Derive the REV address the node derives from an Ethereum address.
pub fn rev_address_from_eth_address(eth_address: &str) -> Result<String, ChainError> {
    let stripped = eth_address
        .strip_prefix("0x")
        .or_else(|| eth_address.strip_prefix("0X"))
        .unwrap_or(eth_address);
    if stripped.len() != ETH_ADDRESS_HEX_LENGTH || !stripped.chars().all(|c| c.is_ascii_hexdigit())
    {
        return Err(ChainError::BadHex(format!(
            "expected a 20-byte hex address, got {eth_address}"
        )));
    }
    let eth_bytes =
        base16::decode(stripped).ok_or_else(|| ChainError::BadHex(eth_address.to_string()))?;
    let key_hash = keccak256::hash(&eth_bytes);

    let mut payload = PREFIX.to_vec();
    payload.extend_from_slice(&key_hash);
    let checksum = blake2b256::hash(&payload);
    payload.extend_from_slice(&checksum[..CHECKSUM_LENGTH]);
    Ok(bs58::encode(payload).into_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sign::KeyPair;

    #[test]
    fn the_node_address_vector_is_reproduced() {
        let key = KeyPair::from_secret_hex(
            "a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76",
        )
        .unwrap();
        assert_eq!(
            key.rev_address().unwrap(),
            "11112VYAt8rUGNRRZX3eJdgagaAhtWTK8Js7F7X5iqddMVqyDTtYau"
        );
    }

    #[test]
    fn eth_addresses_and_public_keys_agree() {
        let key = KeyPair::from_secret_hex(
            "a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76",
        )
        .unwrap();
        let from_pk = key.rev_address().unwrap();
        // The same derivation the wallet uses from MetaMask's account.
        let eth_hash = keccak256::hash(&key.public_bytes()[1..]);
        let eth_hex = base16::encode(&eth_hash);
        let eth_address = &eth_hex[eth_hex.len() - 40..];
        assert_eq!(rev_address_from_eth_address(eth_address).unwrap(), from_pk);
        assert_eq!(
            rev_address_from_eth_address(&format!("0x{eth_address}")).unwrap(),
            from_pk
        );
    }

    #[test]
    fn malformed_addresses_are_refused() {
        assert!(rev_address_from_eth_address("0x1234").is_err());
        assert!(rev_address_from_eth_address(&"z".repeat(40)).is_err());
        assert!(rev_address_from_public_key(&[0x04; 64]).is_err());
        assert!(rev_address_from_public_key(&[0x02; 65]).is_err());
    }
}
