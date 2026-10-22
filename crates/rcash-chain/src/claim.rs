//! Claim secrets and canonical oracle payloads.

use rchain_crypto::hash::blake2b256;
use rchain_shared::base16;

use crate::error::ChainError;

/// Generate a 32-byte claim secret.
///
/// The secret is bearer authority: anyone who sees it can claim the transfer. It is
/// returned as bytes so the caller controls where it goes (a URL fragment, never a log).
pub fn generate_secret() -> Result<[u8; 32], ChainError> {
    let mut secret = [0u8; 32];
    getrandom::fill(&mut secret).map_err(|e| ChainError::Crypto(e.to_string()))?;
    Ok(secret)
}

/// Generate a claim secret as hex.
pub fn generate_secret_hex() -> Result<String, ChainError> {
    Ok(base16::encode(&generate_secret()?))
}

/// The on-chain claim hash: BLAKE2b-256 of the secret bytes, hex-encoded.
pub fn claim_hash(secret_hex: &str) -> Result<String, ChainError> {
    let secret = base16::decode(secret_hex).ok_or_else(|| ChainError::BadHex(secret_hex.into()))?;
    if secret.len() != 32 {
        return Err(ChainError::BadHex(format!(
            "claim secret is {} bytes, expected 32",
            secret.len()
        )));
    }
    Ok(base16::encode(&blake2b256::hash(&secret)))
}

/// The canonical oracle payload the contract hashes before verifying a reporter signature.
pub fn oracle_payload(currency: &str, price: i64, height: i64) -> String {
    format!("rcash:oracle:v1|/root|{currency}|{price}|{height}")
}

/// BLAKE2b-256 of the canonical oracle payload, hex-encoded.
pub fn oracle_digest(currency: &str, price: i64, height: i64) -> String {
    base16::encode(&blake2b256::hash(
        oracle_payload(currency, price, height).as_bytes(),
    ))
}

/// Sign a reporter price with `key`, returning `(public key hex, DER signature hex)`.
pub fn sign_oracle(
    key: &crate::KeyPair,
    currency: &str,
    price: i64,
    height: i64,
) -> Result<(String, String), ChainError> {
    let digest = blake2b256::hash(oracle_payload(currency, price, height).as_bytes());
    let signature = key.sign_prehash(&digest)?;
    Ok((key.public_hex(), base16::encode(&signature)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_claim_hash_is_32_bytes_and_matches_the_contract_rule() {
        let secret = "11".repeat(32);
        let hash = claim_hash(&secret).unwrap();
        assert_eq!(hash.len(), 64);
        // BLAKE2b-256 of 32 0x11 bytes.
        assert_eq!(hash, base16::encode(&blake2b256::hash(&[0x11u8; 32])));
    }

    #[test]
    fn bad_secrets_are_refused() {
        assert!(claim_hash("00").is_err());
        assert!(claim_hash("zz".repeat(32).as_str()).is_err());
    }

    #[test]
    fn the_oracle_payload_is_the_contract_string() {
        assert_eq!(
            oracle_payload("NGN", 66_666, 123),
            "rcash:oracle:v1|/root|NGN|66666|123"
        );
        assert_eq!(generate_secret().unwrap().len(), 32);
    }
}
