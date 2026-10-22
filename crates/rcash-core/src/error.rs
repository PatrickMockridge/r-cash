//! Errors from the pure layer.

/// A domain or encoding error.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum CoreError {
    #[error("amount is not a decimal number: {0}")]
    BadAmount(String),
    #[error("amount has more than 8 fractional digits: {0}")]
    TooManyDecimals(String),
    #[error("amount is out of range: {0}")]
    AmountOutOfRange(String),
    #[error("asset id is invalid: {0}")]
    BadAssetId(String),
    #[error("currency code is invalid: {0}")]
    BadCurrency(String),
    #[error("string cannot be represented in Rholang (contains a double quote): {0}")]
    UnquotableString(String),
    #[error("string contains a control character: {0}")]
    ControlCharacter(String),
    #[error("URI is not a rho:id registry URI: {0}")]
    BadUri(String),
    #[error("term is {actual} bytes; the node limit is {limit} bytes")]
    TermTooLarge { actual: usize, limit: usize },
    #[error("manifest is invalid: {0}")]
    BadManifest(String),
}
