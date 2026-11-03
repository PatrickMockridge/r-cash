//! Fixed-point amounts.
//!
//! Every protocol amount is an integer count of base units, 1 whole unit = 1e8. Nothing
//! in the client performs floating-point arithmetic on money: decimal strings are parsed
//! exactly and rendered exactly. These strings are R-Cash's own input format; they are not
//! Rholang's removed built-in decimal type (rholo issue #527), and no amount is ever
//! serialized as a decimal value.

use serde::{Deserialize, Serialize};

use crate::error::CoreError;
use crate::BASE_UNITS;

/// A signed amount in base units.
///
/// Signed because the same representation is used for intermediate values (deltas,
/// prices); ERTP amounts themselves are non-negative and the node enforces that.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize,
)]
#[serde(transparent)]
pub struct Amount(pub i64);

impl Amount {
    /// Wrap a raw base-unit count.
    pub const fn raw(value: i64) -> Self {
        Self(value)
    }

    /// The raw base-unit count.
    pub const fn value(self) -> i64 {
        self.0
    }

    /// Whole units as an exact amount (for example `Amount::whole(3)` is 3.00000000).
    pub fn whole(units: i64) -> Option<Self> {
        units.checked_mul(BASE_UNITS).map(Self)
    }

    /// Parse a decimal string such as `"12"`, `"0.5"` or `"-1.25"`.
    ///
    /// At most eight fractional digits; extra digits are refused rather than rounded.
    pub fn parse(input: &str) -> Result<Self, CoreError> {
        let text = input.trim();
        if text.is_empty() {
            return Err(CoreError::BadAmount(input.to_string()));
        }
        let (negative, digits) = match text.strip_prefix('-') {
            Some(rest) => (true, rest),
            None => (false, text.strip_prefix('+').unwrap_or(text)),
        };
        if digits.is_empty() {
            return Err(CoreError::BadAmount(input.to_string()));
        }
        let (whole_text, frac_text) = match digits.split_once('.') {
            Some((whole, frac)) => (whole, frac),
            None => (digits, ""),
        };
        if whole_text.is_empty() && frac_text.is_empty() {
            return Err(CoreError::BadAmount(input.to_string()));
        }
        if !whole_text.chars().all(|c| c.is_ascii_digit())
            || !frac_text.chars().all(|c| c.is_ascii_digit())
        {
            return Err(CoreError::BadAmount(input.to_string()));
        }
        if frac_text.len() > 8 {
            return Err(CoreError::TooManyDecimals(input.to_string()));
        }

        let whole: i64 = if whole_text.is_empty() {
            0
        } else {
            whole_text
                .parse()
                .map_err(|_| CoreError::AmountOutOfRange(input.to_string()))?
        };
        let mut frac: i64 = if frac_text.is_empty() {
            0
        } else {
            frac_text
                .parse()
                .map_err(|_| CoreError::BadAmount(input.to_string()))?
        };
        // Right-pad the fraction to eight digits without floating point.
        for _ in frac_text.len()..8 {
            frac *= 10;
        }

        let magnitude = whole
            .checked_mul(BASE_UNITS)
            .and_then(|v| v.checked_add(frac))
            .ok_or_else(|| CoreError::AmountOutOfRange(input.to_string()))?;
        Ok(Self(if negative { -magnitude } else { magnitude }))
    }

    /// Render exactly, trimming trailing fractional zeros but keeping at least one digit
    /// when the value is not whole (so `0.5` never prints as `0.`).
    pub fn to_decimal(self) -> String {
        let value = self.0 as i128;
        let sign = if value < 0 { "-" } else { "" };
        let magnitude = value.unsigned_abs();
        let whole = magnitude / BASE_UNITS as u128;
        let frac = magnitude % BASE_UNITS as u128;
        if frac == 0 {
            format!("{sign}{whole}")
        } else {
            let frac = format!("{frac:08}");
            format!("{sign}{whole}.{}", frac.trim_end_matches('0'))
        }
    }
}

impl std::fmt::Display for Amount {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.to_decimal())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_and_renders_exactly() {
        assert_eq!(Amount::parse("1").unwrap().value(), 100_000_000);
        assert_eq!(Amount::parse("0.00000001").unwrap().value(), 1);
        assert_eq!(Amount::parse("12.5").unwrap().to_decimal(), "12.5");
        assert_eq!(Amount::parse("-0.25").unwrap().to_decimal(), "-0.25");
        assert_eq!(Amount::parse("+3").unwrap().value(), 300_000_000);
        assert_eq!(Amount::parse("3").unwrap().to_decimal(), "3");
    }

    #[test]
    fn refuses_rounding_and_junk() {
        assert_eq!(
            Amount::parse("0.123456789"),
            Err(CoreError::TooManyDecimals("0.123456789".to_string()))
        );
        assert!(Amount::parse("1.2.3").is_err());
        assert!(Amount::parse("").is_err());
        assert!(Amount::parse(".").is_err());
        assert!(Amount::parse("1e8").is_err());
        assert!(Amount::parse("0x10").is_err());
        assert!(Amount::parse("99999999999999999999").is_err());
    }

    #[test]
    fn whole_units_do_not_overflow_silently() {
        assert_eq!(Amount::whole(2).unwrap().value(), 200_000_000);
        assert!(Amount::whole(i64::MAX).is_none());
    }
}
