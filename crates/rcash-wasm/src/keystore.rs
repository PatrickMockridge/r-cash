//! Web3 Secret Storage v3 keystore encryption.
//!
//! The format is the one MetaMask/Ethereum wallets use: scrypt-derived key, AES-128-CTR
//! ciphertext, keccak MAC. R-Cash uses it so a wallet file is portable and familiar, not
//! because it is an Ethereum wallet.
//!
//! The secret never leaves this module in plaintext: the UI receives the keystore JSON and
//! stores that in IndexedDB.

use aes::Aes128;
use ctr::cipher::{KeyIvInit, StreamCipher};
use getrandom::fill;
use serde::{Deserialize, Serialize};
use sha3::{Digest, Keccak256};
use zeroize::Zeroize;

type Aes128Ctr = ctr::Ctr128BE<Aes128>;

/// scrypt cost. `n = 2^14` is a deliberate browser-friendly choice: `2^18` costs seconds
/// on a phone. The parameter is stored in the file, so raising it later stays compatible.
const LOG_N: u8 = 14;
const R: u32 = 8;
const P: u32 = 1;

#[derive(Serialize, Deserialize)]
struct Keystore {
    version: u32,
    id: String,
    address: String,
    crypto: Crypto,
}

#[derive(Serialize, Deserialize)]
struct Crypto {
    ciphertext: String,
    cipherparams: CipherParams,
    cipher: String,
    kdf: String,
    kdfparams: KdfParams,
    mac: String,
}

#[derive(Serialize, Deserialize)]
struct CipherParams {
    iv: String,
}

#[derive(Serialize, Deserialize)]
struct KdfParams {
    dklen: u32,
    n: u32,
    r: u32,
    p: u32,
    salt: String,
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn unhex(text: &str) -> Result<Vec<u8>, String> {
    if !text.len().is_multiple_of(2) || !text.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err("keystore field is not hex".into());
    }
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).map_err(|e| e.to_string()))
        .collect()
}

/// Encrypt a 32-byte secret into a Web3 v3 keystore document.
pub fn encrypt(secret: &[u8], address_hex: &str, password: &str) -> Result<String, String> {
    if secret.len() != 32 {
        return Err("secret is not 32 bytes".into());
    }
    let mut salt = [0u8; 32];
    let mut iv = [0u8; 16];
    let mut id = [0u8; 16];
    fill(&mut salt).map_err(|e| e.to_string())?;
    fill(&mut iv).map_err(|e| e.to_string())?;
    fill(&mut id).map_err(|e| e.to_string())?;

    let mut derived = [0u8; 32];
    let params = scrypt::Params::new(LOG_N, R, P).map_err(|e| e.to_string())?;
    scrypt::scrypt(password.as_bytes(), &salt, &params, &mut derived).map_err(|e| e.to_string())?;

    let mut ciphertext = secret.to_vec();
    let mut cipher = Aes128Ctr::new_from_slices(&derived[..16], &iv).map_err(|e| e.to_string())?;
    cipher.apply_keystream(&mut ciphertext);

    let mut mac_input = derived[16..32].to_vec();
    mac_input.extend_from_slice(&ciphertext);
    let mac = Keccak256::digest(&mac_input);
    derived.zeroize();

    let keystore = Keystore {
        version: 3,
        id: hex(&id),
        address: address_hex.to_ascii_lowercase(),
        crypto: Crypto {
            ciphertext: hex(&ciphertext),
            cipherparams: CipherParams { iv: hex(&iv) },
            cipher: "aes-128-ctr".into(),
            kdf: "scrypt".into(),
            kdfparams: KdfParams {
                dklen: 32,
                n: 1 << LOG_N,
                r: R,
                p: P,
                salt: hex(&salt),
            },
            mac: hex(&mac),
        },
    };
    serde_json::to_string(&keystore).map_err(|e| e.to_string())
}

/// Decrypt a Web3 v3 keystore document, returning the 32-byte secret.
pub fn decrypt(document: &str, password: &str) -> Result<[u8; 32], String> {
    let keystore: Keystore =
        serde_json::from_str(document).map_err(|e| format!("not a keystore: {e}"))?;
    if keystore.version != 3 {
        return Err(format!("unsupported keystore version {}", keystore.version));
    }
    if keystore.crypto.cipher != "aes-128-ctr" || keystore.crypto.kdf != "scrypt" {
        return Err("unsupported keystore cipher/kdf".into());
    }
    let kdf = &keystore.crypto.kdfparams;
    if kdf.n == 0 || !kdf.n.is_power_of_two() || kdf.dklen != 32 {
        return Err("unsupported scrypt parameters".into());
    }
    let log_n = kdf.n.trailing_zeros() as u8;
    if log_n == 0 || log_n > 20 {
        return Err("unsupported scrypt cost".into());
    }
    let salt = unhex(&kdf.salt)?;
    let iv = unhex(&keystore.crypto.cipherparams.iv)?;
    let ciphertext = unhex(&keystore.crypto.ciphertext)?;
    if iv.len() != 16 || ciphertext.len() != 32 {
        return Err("bad keystore lengths".into());
    }

    let mut derived = [0u8; 32];
    let params = scrypt::Params::new(log_n, kdf.r, kdf.p).map_err(|e| e.to_string())?;
    scrypt::scrypt(password.as_bytes(), &salt, &params, &mut derived).map_err(|e| e.to_string())?;

    let mut mac_input = derived[16..32].to_vec();
    mac_input.extend_from_slice(&ciphertext);
    let mac = Keccak256::digest(&mac_input);
    if hex(&mac) != keystore.crypto.mac.to_ascii_lowercase() {
        derived.zeroize();
        return Err("wrong password or corrupt keystore".into());
    }

    let mut secret = ciphertext;
    let mut cipher = Aes128Ctr::new_from_slices(&derived[..16], &iv).map_err(|e| e.to_string())?;
    cipher.apply_keystream(&mut secret);
    derived.zeroize();
    secret
        .try_into()
        .map_err(|_| "decrypted secret is not 32 bytes".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trips_and_rejects_the_wrong_password() {
        let secret = [7u8; 32];
        let document = encrypt(
            &secret,
            "00112233445566778899aabbccddeeff00112233",
            "hunter2",
        )
        .expect("encrypt");
        let json: serde_json::Value = serde_json::from_str(&document).unwrap();
        assert_eq!(json["version"], 3);
        assert_eq!(json["crypto"]["kdf"], "scrypt");
        assert_eq!(json["crypto"]["cipher"], "aes-128-ctr");
        assert_eq!(decrypt(&document, "hunter2").unwrap(), secret);
        assert!(decrypt(&document, "wrong").is_err());
    }

    #[test]
    fn refuses_a_tampered_mac() {
        let document =
            encrypt(&[1u8; 32], "00112233445566778899aabbccddeeff00112233", "pw").unwrap();
        let tampered = document.replace("\"mac\":\"", "\"mac\":\"00");
        assert!(decrypt(&tampered, "pw").is_err());
    }
}
