//! Derive REV addresses from uncompressed public keys.
//!
//! Usage: cargo run -p rcash-chain --example rev_address -- <pubkey-hex>...
//!
//! Useful when reconstructing a testnet's genesis wallets from its validator
//! public keys without a running node.

fn main() {
    for arg in std::env::args().skip(1) {
        let bytes: Vec<u8> = (0..arg.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&arg[i..i + 2], 16).expect("hex"))
            .collect();
        match rcash_chain::address::rev_address_from_public_key(&bytes) {
            Ok(address) => println!("{address}"),
            Err(error) => println!("error: {error}"),
        }
    }
}
