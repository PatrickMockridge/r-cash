//! Safe construction of Rholang source fragments.
//!
//! The Rholang lexer does not process escapes: a string token runs from one `"` to the
//! next `"` (`rholang/src/parser.rs`), and the normalizer only strips the quotes. There
//! is therefore no way to represent a double quote inside a string literal, and
//! backslash sequences are two literal characters. This module refuses such input
//! instead of producing a term that parses as something else.

use crate::assets::RegistryUri;
use crate::error::CoreError;

/// The node's maximum deploy term size, inclusive (`MAX_DEPLOY_TERM_BYTES`).
pub const MAX_TERM_BYTES: usize = 64 * 1024;

/// Quote a string for a Rholang term.
///
/// Refuses `"` (unrepresentable) and control characters (the protocol never needs them,
/// and the lexer treats them literally).
pub fn quote_str(value: &str) -> Result<String, CoreError> {
    if value.contains('"') {
        return Err(CoreError::UnquotableString(value.to_string()));
    }
    if value.chars().any(char::is_control) {
        return Err(CoreError::ControlCharacter(value.to_string()));
    }
    Ok(format!("\"{value}\""))
}

/// Quote a registry URI as a backtick literal.
pub fn quote_uri(uri: &RegistryUri) -> String {
    format!("`{}`", uri.as_str())
}

/// Emit a byte array from lowercase hex: `"abcd".hexToBytes()`.
///
/// The hex is validated so a caller cannot smuggle a quote into the literal.
pub fn hex_bytes(hex: &str) -> Result<String, CoreError> {
    if hex.is_empty() || !hex.len().is_multiple_of(2) || !hex.chars().all(|c| c.is_ascii_hexdigit())
    {
        return Err(CoreError::UnquotableString(format!("not hex: {hex}")));
    }
    Ok(format!("\"{hex}\".hexToBytes()"))
}

/// Refuse a term the node will reject for size before it is signed.
pub fn check_term_size(term: &str) -> Result<(), CoreError> {
    let actual = term.len();
    if actual > MAX_TERM_BYTES {
        return Err(CoreError::TermTooLarge {
            actual,
            limit: MAX_TERM_BYTES,
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strings_are_quoted_raw_and_refuse_quotes() {
        assert_eq!(quote_str("NGN").unwrap(), "\"NGN\"");
        assert_eq!(quote_str("a b").unwrap(), "\"a b\"");
        assert_eq!(
            quote_str("a\"b"),
            Err(CoreError::UnquotableString("a\"b".to_string()))
        );
        assert!(quote_str("a\nb").is_err());
    }

    #[test]
    fn hex_is_validated() {
        assert_eq!(hex_bytes("00ff").unwrap(), "\"00ff\".hexToBytes()");
        assert!(hex_bytes("0").is_err());
        assert!(hex_bytes("zz").is_err());
    }

    #[test]
    fn size_limit_is_inclusive_and_bounded() {
        assert!(check_term_size(&"a".repeat(MAX_TERM_BYTES)).is_ok());
        assert_eq!(
            check_term_size(&"a".repeat(MAX_TERM_BYTES + 1)),
            Err(CoreError::TermTooLarge {
                actual: MAX_TERM_BYTES + 1,
                limit: MAX_TERM_BYTES
            })
        );
    }
}
