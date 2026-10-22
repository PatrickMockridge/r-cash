//! Pure domain layer for R-Cash: amounts, assets, Rholang term encoding and the
//! deployment manifest.
//!
//! No I/O, no network, no keys. Everything here is shared by the native CLI and the
//! browser WASM module.

pub mod assets;
pub mod error;
pub mod manifest;
pub mod rho;
pub mod units;

pub use assets::{AssetId, Currency, RegistryUri};
pub use error::CoreError;
pub use units::Amount;

/// The scale of every protocol amount: 1 whole unit = 100,000,000 base units.
pub const BASE_UNITS: i64 = 100_000_000;
