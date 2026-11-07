//! Claim secrets and canonical oracle payloads.

use rchain_crypto::hash::blake2b256;
use rchain_shared::base16;

use crate::error::ChainError;

/// The canonical claim-commitment schema.
pub const CLAIM_SCHEMA: &str = "rcash:claim:v1";

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

/// The canonical claim preimage over `[opId, assetId, amount, secretHex]`.
///
/// Mirrors `TransferContract@"claim"` in `contracts/src/deploy/v3/40_transfer.rho`,
/// which hashes this form with `Codec@"hash"` under schema `rcash:claim:v1`.
/// `opId` is the caller-supplied operation id, not the account-allocated
/// transfer id; `amount` is the escrowed base-unit integer in decimal; the
/// secret is the lowercase hex of its bytes.
pub fn claim_payload(
    op_id: &str,
    asset: &str,
    amount: i64,
    secret_hex: &str,
) -> Result<String, ChainError> {
    let secret = base16::decode(secret_hex).ok_or_else(|| ChainError::BadHex(secret_hex.into()))?;
    if secret.len() != 32 {
        return Err(ChainError::BadHex(format!(
            "claim secret is {} bytes, expected 32",
            secret.len()
        )));
    }
    let secret_hex = base16::encode(&secret).to_ascii_lowercase();
    Ok(rcash_core::market::encode(
        CLAIM_SCHEMA,
        &[
            op_id.to_string(),
            asset.to_string(),
            amount.to_string(),
            secret_hex,
        ],
    ))
}

/// The on-chain claim hash: BLAKE2b-256 of the canonical claim preimage,
/// hex-encoded.
pub fn claim_hash(
    op_id: &str,
    asset: &str,
    amount: i64,
    secret_hex: &str,
) -> Result<String, ChainError> {
    Ok(base16::encode(&blake2b256::hash(
        claim_payload(op_id, asset, amount, secret_hex)?.as_bytes(),
    )))
}

/// The legacy v0.4 claim hash: BLAKE2b-256 of the secret bytes, hex-encoded.
///
/// `contracts/src/transfer/TransferBook.rho` (the v0.4 `AccountBody` path)
/// still compares this raw digest. The canonical `rcash:claim:v1` preimage
/// applies only to `contracts/src/deploy/v3/40_transfer.rho`; this helper is
/// retained for the legacy send path, which the campaign did not change.
pub fn legacy_secret_digest(secret_hex: &str) -> Result<String, ChainError> {
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
    fn a_claim_hash_matches_the_canonical_contract_rule() {
        let secret = "11".repeat(32);
        let payload = claim_payload("memo-op-1", "REV", 5_000_000, &secret).unwrap();
        assert_eq!(
            payload,
            "rcash:claim:v1|9:memo-op-1|3:REV|7:5000000|\
             64:1111111111111111111111111111111111111111111111111111111111111111"
        );
        // Blake2b-256 of the canonical UTF-8 preimage.
        assert_eq!(
            claim_hash("memo-op-1", "REV", 5_000_000, &secret).unwrap(),
            "e52be29d59b30ad43cddad78f186d8381a94f3090af5c01260c06a0cea8626e8"
        );
        // The preimage always carries lowercase hex, like Rholang `bytesToHex`.
        assert_eq!(
            claim_payload("memo-op-1", "REV", 5_000_000, &secret.to_uppercase()).unwrap(),
            payload
        );
    }

    #[test]
    fn a_claim_length_counts_characters_not_utf8_bytes() {
        // "mémo" is 4 Unicode scalar values but 5 UTF-8 bytes; the length
        // prefix must follow Rholang `String.length()`.
        let secret = "22".repeat(32);
        assert_eq!(
            claim_payload("mémo", "REV", 1, &secret).unwrap(),
            "rcash:claim:v1|4:mémo|3:REV|1:1|\
             64:2222222222222222222222222222222222222222222222222222222222222222"
        );
        assert_eq!(
            claim_hash("mémo", "REV", 1, &secret).unwrap(),
            "ef0d7ccaf87981a88b4691909c2ef175cb72288c44d92c6f341ac57135f3cbee"
        );
    }

    #[test]
    fn bad_secrets_are_refused() {
        assert!(claim_hash("", "REV", 1, "00").is_err());
        assert!(claim_hash("", "REV", 1, "zz".repeat(32).as_str()).is_err());
    }

    #[test]
    fn the_legacy_v04_digest_stays_raw() {
        let secret = "11".repeat(32);
        assert_eq!(
            legacy_secret_digest(&secret).unwrap(),
            base16::encode(&blake2b256::hash(&[0x11u8; 32]))
        );
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
