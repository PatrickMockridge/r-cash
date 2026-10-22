//! secp256k1 keys and deploy signing.
//!
//! Uses `rchain_crypto::signatures::Signed::new`, which is the node's own signing path:
//! prost-encode, hash per algorithm (BLAKE2b-256 for `secp256k1`), RFC-6979 DER low-S,
//! 65-byte uncompressed public key. A deploy id is the hex DER signature.

use rchain_crypto::private_key::PrivateKey;
use rchain_crypto::signatures::signatures_alg::from_algorithm;
use rchain_crypto::signatures::signed::Signed;
use rchain_models::casper::protocol::casper_message::DeployData;
use rchain_shared::base16;
use zeroize::Zeroize;

use crate::address::rev_address_from_public_key;
use crate::error::ChainError;

/// A secp256k1 key pair held in memory. The secret is zeroized on drop.
pub struct KeyPair {
    secret: Vec<u8>,
    public: Vec<u8>,
}

impl std::fmt::Debug for KeyPair {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "KeyPair(<secret redacted>)")
    }
}

impl Drop for KeyPair {
    fn drop(&mut self) {
        self.secret.zeroize();
    }
}

impl KeyPair {
    /// Build from a 32-byte secret.
    pub fn from_secret_bytes(secret: &[u8]) -> Result<Self, ChainError> {
        if secret.len() != 32 {
            return Err(ChainError::BadKey(format!(
                "secret key is {} bytes, expected 32",
                secret.len()
            )));
        }
        let alg = algorithm()?;
        if !rchain_crypto::signatures::secp256k1::Secp256k1::sec_key_verify(secret) {
            return Err(ChainError::BadKey("not a valid secp256k1 scalar".into()));
        }
        let public = alg
            .to_public(&PrivateKey::new(secret.to_vec()))
            .map_err(|e| ChainError::Crypto(e.to_string()))?;
        Ok(Self {
            secret: secret.to_vec(),
            public: public.bytes().to_vec(),
        })
    }

    /// Build from a hex-encoded 32-byte secret.
    pub fn from_secret_hex(hex: &str) -> Result<Self, ChainError> {
        let bytes = base16::decode(hex).ok_or_else(|| ChainError::BadHex(hex.to_string()))?;
        Self::from_secret_bytes(&bytes)
    }

    /// Generate a fresh key pair.
    pub fn generate() -> Result<Self, ChainError> {
        let (secret, public) = algorithm()?.new_key_pair();
        Ok(Self {
            secret: secret.bytes().to_vec(),
            public: public.bytes().to_vec(),
        })
    }

    /// The hex-encoded secret. Handle with care; never log it.
    pub fn secret_hex(&self) -> String {
        base16::encode(&self.secret)
    }

    /// The hex-encoded 65-byte uncompressed public key.
    pub fn public_hex(&self) -> String {
        base16::encode(&self.public)
    }

    /// The raw 65-byte public key.
    pub fn public_bytes(&self) -> &[u8] {
        &self.public
    }

    /// The REV address of this key.
    pub fn rev_address(&self) -> Result<String, ChainError> {
        rev_address_from_public_key(&self.public)
    }

    /// Sign a deploy, producing the wire form.
    pub fn sign_deploy(&self, data: DeployData) -> Result<SignedDeploy, ChainError> {
        let alg = algorithm()?;
        let signed = Signed::new(data, alg, &PrivateKey::new(self.secret.clone()))
            .map_err(|e| ChainError::Crypto(e.to_string()))?;
        let signature_hex = base16::encode(&signed.sig);
        Ok(SignedDeploy {
            data: signed.data,
            deployer_hex: base16::encode(signed.pk.bytes()),
            deploy_id: signature_hex.clone(),
            signature_hex,
            sig_algorithm: signed.sig_algorithm.name().to_string(),
        })
    }

    /// Sign a 32-byte prehash (oracle and admin payloads use this shape).
    pub fn sign_prehash(&self, prehash: &[u8]) -> Result<Vec<u8>, ChainError> {
        if prehash.len() != 32 {
            return Err(ChainError::Crypto(format!(
                "prehash is {} bytes, expected 32",
                prehash.len()
            )));
        }
        rchain_crypto::signatures::secp256k1::Secp256k1::sign_bytes(prehash, &self.secret)
            .map_err(|e| ChainError::Crypto(e.to_string()))
    }

    /// Verify a DER signature over a 32-byte prehash with this key's public half.
    pub fn verify_prehash(&self, prehash: &[u8], signature: &[u8]) -> bool {
        rchain_crypto::signatures::secp256k1::Secp256k1::verify_bytes(
            prehash,
            signature,
            &self.public,
        )
    }
}

fn algorithm(
) -> Result<&'static dyn rchain_crypto::signatures::signatures_alg::SignaturesAlg, ChainError> {
    from_algorithm("secp256k1").ok_or_else(|| ChainError::Crypto("secp256k1 unavailable".into()))
}

/// A deploy ready to POST to the node.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SignedDeploy {
    pub data: DeployData,
    pub deployer_hex: String,
    pub signature_hex: String,
    pub sig_algorithm: String,
    /// The deploy id: hex of the DER signature.
    pub deploy_id: String,
}

impl SignedDeploy {
    /// The exact bytes that were signed (the node's DeployData protobuf encoding).
    pub fn encoded_bytes(&self) -> Vec<u8> {
        <DeployData as rchain_shared::serialize::Serialize<DeployData>>::encode(&self.data)
    }

    /// Hex of the signed bytes, for golden fixture comparison.
    pub fn encoded_hex(&self) -> String {
        base16::encode(&self.encoded_bytes())
    }

    /// The request body `POST /api/v1/deploy` expects.
    pub fn request_body(&self) -> serde_json::Value {
        serde_json::json!({
            "data": self.data,
            "deployer": self.deployer_hex,
            "signature": self.signature_hex,
            "sigAlgorithm": self.sig_algorithm,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::deploy::DeployOptions;

    #[test]
    fn signing_is_deterministic_and_verifies() {
        let key = KeyPair::from_secret_hex(
            "a68a6e6cca30f81bd24a719f3145d20e8424bd7b396309b0708a16c7d8000b76",
        )
        .unwrap();
        let data = DeployOptions::new("Nil")
            .timestamp(1_700_000_000_000)
            .phlo(1_000_000, 1)
            .shard_id("/root")
            .build()
            .unwrap();
        let a = key.sign_deploy(data.clone()).unwrap();
        let b = key.sign_deploy(data).unwrap();
        assert_eq!(a.signature_hex, b.signature_hex);
        assert_eq!(a.deploy_id, a.signature_hex);
        assert_eq!(a.sig_algorithm, "secp256k1");
        assert_eq!(a.deployer_hex, key.public_hex());
        let sig = base16::decode(&a.signature_hex).unwrap();
        let prehash = rchain_crypto::signatures::signed::signature_hash(
            "secp256k1",
            &<DeployData as rchain_shared::serialize::Serialize<DeployData>>::encode(&a.data),
        );
        assert!(key.verify_prehash(&prehash, &sig));
    }

    /// The node's own known-answer test (`crypto/src/signatures/secp256k1.rs`).
    #[test]
    fn the_node_secp256k1_vector_is_reproduced() {
        let data = rchain_crypto::hash::sha256::hash(b"testing");
        let secret =
            base16::decode("67E56582298859DDAE725F972992A07C6C4FB9F62A8FFF58CE3CA926A1063530")
                .unwrap();
        let signature =
            rchain_crypto::signatures::secp256k1::Secp256k1::sign_bytes(&data, &secret).unwrap();
        assert_eq!(
            base16::encode(&signature).to_uppercase(),
            "30440220182A108E1448DC8F1FB467D06A0F3BB8EA0533584CB954EF8DA112F1D60E39A202201C66F36DA211C087F3AF88B50EDF4F9BDAA6CF5FD6817E74DCA34DB12390C6E9"
        );
    }

    #[test]
    fn bad_secrets_are_refused() {
        assert!(KeyPair::from_secret_bytes(&[1; 31]).is_err());
        assert!(KeyPair::from_secret_bytes(&[0; 32]).is_err());
        assert!(KeyPair::from_secret_hex("zz").is_err());
    }

    #[test]
    fn generated_keys_have_65_byte_public_keys() {
        let key = KeyPair::generate().unwrap();
        assert_eq!(key.public_bytes().len(), 65);
        assert_eq!(key.public_bytes()[0], 0x04);
        assert!(key.rev_address().unwrap().starts_with("1111"));
    }
}
