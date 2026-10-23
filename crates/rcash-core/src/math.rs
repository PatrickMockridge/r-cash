//! Fixed-point arithmetic mirroring the protocol.
//!
//! All values are integers. Outputs and shares round down; fees round up. Every
//! intermediate is `i128` so a product cannot wrap, and the result must fit `i64`.

use crate::BASE_UNITS;

/// Basis points: 10,000 = 100%.
pub const BPS: i64 = 10_000;

/// `a * b / d`, rounded toward negative infinity.
pub fn mul_div(a: i64, b: i64, d: i64) -> Option<i64> {
    if d == 0 {
        return None;
    }
    let n = a as i128 * b as i128;
    let d = d as i128;
    let mut q = n / d;
    let r = n % d;
    if r != 0 && ((r > 0) != (d > 0)) {
        q -= 1;
    }
    i64::try_from(q).ok()
}

/// `a * b / d`, rounded toward positive infinity.
pub fn mul_div_up(a: i64, b: i64, d: i64) -> Option<i64> {
    if d == 0 {
        return None;
    }
    let n = a as i128 * b as i128;
    let d = d as i128;
    let mut q = n / d;
    let r = n % d;
    if r != 0 && ((r > 0) == (d > 0)) {
        q += 1;
    }
    i64::try_from(q).ok()
}

/// Checked addition.
pub fn add(a: i64, b: i64) -> Option<i64> {
    a.checked_add(b)
}

/// Checked subtraction.
pub fn sub(a: i64, b: i64) -> Option<i64> {
    a.checked_sub(b)
}

/// The cross rate: quote base units per one base unit, scaled by 1e8.
pub fn cross_rate(price_base: i64, price_quote: i64) -> Option<i64> {
    mul_div(price_base, BASE_UNITS, price_quote)
}

/// A basis-point share of an amount, rounded down.
pub fn bps_of(amount: i64, bps: i64) -> Option<i64> {
    mul_div(amount, bps, BPS)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cross_rate_matches_the_launch_corridor() {
        // NGN/USD = 0.00066666, KES/USD = 0.00769230.
        assert_eq!(cross_rate(66_666, 769_230).unwrap(), 8_666_588);
    }

    #[test]
    fn rounding_is_directional() {
        assert_eq!(mul_div(5, 1, 2), Some(2));
        assert_eq!(mul_div_up(5, 1, 2), Some(3));
        assert_eq!(mul_div(-5, 1, 2), Some(-3));
        assert_eq!(mul_div_up(-5, 1, 2), Some(-2));
        assert_eq!(mul_div(1, 1, 0), None);
    }

    #[test]
    fn no_overflow_silently_wraps() {
        assert_eq!(mul_div(i64::MAX, 2, 1), None);
        assert_eq!(bps_of(100_000_000, 20), Some(200_000));
    }
}
