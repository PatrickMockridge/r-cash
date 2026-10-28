import unittest

from hypothesis import given, settings, strategies as st

from model import (
    Buffer, Savings, cover, pay_savings, s10, savings_deposit, savings_value,
    savings_withdraw,
)


class BufferSavingsTest(unittest.TestCase):
    @given(amount=st.integers(1, 10**8), shares=st.integers(1, 10**8))
    @settings(max_examples=80, deadline=None)
    def test_deposit_conserves_shares(self, amount, shares):
        start = Savings(0, 0, {})
        end = savings_deposit(start, "a", amount, shares)
        self.assertTrue(s10(end))
        self.assertEqual(end.total_shares, start.total_shares + shares)

    @given(total_shares=st.integers(1, 10**8), total_assets=st.integers(1, 10**9),
           held=st.integers(1, 10**8), shares=st.integers(1, 10**8))
    @settings(max_examples=80, deadline=None)
    def test_withdraw_conserves_or_refuses(self, total_shares, total_assets, held, shares):
        shares = min(shares, held)
        start = Savings(held, total_assets, {"a": held})
        amount = savings_value(total_assets, held, shares)
        end = savings_withdraw(start, "a", shares, amount)
        self.assertTrue(s10(end))

    @given(surplus=st.integers(0, 10**9), sin=st.integers(0, 10**9),
           bad=st.integers(0, 10**9), bps=st.integers(0, 10000))
    @settings(max_examples=100, deadline=None)
    def test_waterfall_never_overspends(self, surplus, sin, bad, bps):
        start = Buffer(surplus, sin, bps)
        covered, cancelled = cover(start, bad)
        self.assertLessEqual(covered.surplus, surplus)
        self.assertEqual(cancelled, min(surplus, sin + bad))
        paid, moved = pay_savings(covered)
        self.assertLessEqual(paid.surplus, covered.surplus)
        self.assertLessEqual(moved, covered.surplus)


if __name__ == "__main__":
    unittest.main()
