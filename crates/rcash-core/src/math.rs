//! Fixed-point arithmetic mirroring the protocol.
//!
//! All values are integers. Outputs and shares round down; debts, fees and required
//! collateral round up. Every intermediate is `i128` so a product cannot wrap, and the
//! result must fit `i64`.

use crate::BASE_UNITS;

/// Basis points: 10,000 = 100%.
pub const BPS: i64 = 10_000;
/// The per-block interest denominator.
pub const INTEREST_SCALE: i64 = 1_000_000_000_000;

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

/// REV collateral valued in local base units: `collateral * P_REV / P_LOCAL`.
pub fn collateral_local(collateral_drops: i64, price_rev: i64, price_local: i64) -> Option<i64> {
    mul_div(collateral_drops, price_rev, price_local)
}

/// REV drops needed to cover a local-currency debt.
pub fn rev_needed(debt_local: i64, price_local: i64, price_rev: i64) -> Option<i64> {
    mul_div_up(debt_local, price_local, price_rev)
}

/// The collateral test without division: `collateral * 10_000 >= debt * mcr_bps`.
pub fn is_healthy(collateral_local: i64, debt: i64, mcr_bps: i64) -> bool {
    let left = collateral_local as i128 * BPS as i128;
    let right = debt as i128 * mcr_bps as i128;
    left >= right
}

/// Simple per-block interest, rounded up: `debt * rate_per_block * blocks / 1e12`.
pub fn accrued_interest(debt: i64, rate_per_block: i64, blocks: i64) -> Option<i64> {
    let product = mul_div(rate_per_block, blocks, 1)?;
    mul_div_up(debt, product, INTEREST_SCALE)
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
    fn collateral_and_health_match_the_seeded_vault() {
        // 8 REV at 5 USD, NGN at 0.00066666, 300 NGN debt, 200% MCR.
        let local = collateral_local(800_000_000, 5_000_000, 66_666).unwrap();
        assert_eq!(local, 60_000_600_006);
        assert!(is_healthy(local, 30_000_000_000, 20_000));
        // One base unit less fails only once the buffer is gone; check the boundary itself.
        assert!(is_healthy(60_000_000_000, 30_000_000_000, 20_000));
        assert!(!is_healthy(59_999_999_999, 30_000_000_000, 20_000));
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
    fn interest_rounds_up_and_averages_over_blocks() {
        assert_eq!(accrued_interest(0, 1, 100), Some(0));
        // 3171 per block over 1e12 on 1e8 debt, one block: ceil(317100/1e12) = 1.
        assert_eq!(accrued_interest(100_000_000, 3_171, 1), Some(1));
        // Ten blocks: ceil(3.171) base units = 4.
        assert_eq!(accrued_interest(100_000_000, 3_171, 10), Some(4));
        // 1e12 debt, one block: 3171 exactly.
        assert_eq!(accrued_interest(1_000_000_000_000, 3_171, 1), Some(3_171));
    }

    #[test]
    fn no_overflow_silently_wraps() {
        assert_eq!(mul_div(i64::MAX, 2, 1), None);
        assert_eq!(bps_of(100_000_000, 20), Some(200_000));
    }
}
