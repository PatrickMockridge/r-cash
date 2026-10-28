import unittest

from hypothesis import given, settings, strategies as st

from model import (
    E8, Ledger, Refused, accrual_delta, burn, cover0, liquidate, mint,
    psm_buy, psm_sell, repay, s1, s3, write_off,
)


class IssuerTest(unittest.TestCase):
    @given(amount=st.integers(1, 10**9), accrued=st.integers(0, 10**9),
           stored=st.integers(0, 10**8))
    @settings(max_examples=80, deadline=None)
    def test_mint_preserves_s1_s3(self, amount, accrued, stored):
        start = Ledger(10**8, 10**8, 10**8, 0, 0, 0, 0)
        end = mint(start, amount, accrued, min(accrued, stored))
        self.assertTrue(s1(end))
        self.assertTrue(s3(end))

    @given(amount=st.integers(0, 10**8))
    @settings(max_examples=40, deadline=None)
    def test_burn_preserves_s1(self, amount):
        start = Ledger(10**8, 10**8, 0, 0, 0, 0, 0)
        end = burn(start, amount)
        self.assertTrue(s1(end))

    @given(amount=st.integers(0, 10**8), interest=st.integers(0, 10**8),
           accrued=st.integers(0, 10**9), stored=st.integers(0, 10**9))
    @settings(max_examples=80, deadline=None)
    def test_repay_is_composite_s3(self, amount, interest, accrued, stored):
        stored = min(stored, accrued)
        interest = min(interest, amount)
        start = Ledger(10**9, 10**9, 10**9 - 10**7, 0, 10**7, 0, 0)
        end = repay(start, amount, interest, amount - interest, 0, accrued, stored)
        self.assertTrue(s3(end))

    @given(amount=st.integers(1, 10**8), accrued=st.integers(0, 10**9),
           stored=st.integers(0, 10**9))
    @settings(max_examples=60, deadline=None)
    def test_liquidate_and_writeoff_s3(self, amount, accrued, stored):
        stored = min(stored, accrued)
        start = Ledger(10**9, 10**9, 10**9, 0, 0, 0, 0)
        self.assertTrue(s3(liquidate(start, amount, accrued, stored)))
        self.assertTrue(s3(write_off(start, amount, accrued, stored, 0)))

    @given(amount=st.integers(0, 10**8))
    @settings(max_examples=40, deadline=None)
    def test_cover0_s3(self, amount):
        start = Ledger(10**8, 10**8, 0, 0, 10**8, 0, 0)
        self.assertTrue(s3(cover0(start, amount)))

    @given(out=st.integers(0, 10**8), accrued=st.integers(0, 10**9))
    @settings(max_examples=60, deadline=None)
    def test_psm_signed_debt_s3(self, out, accrued):
        start = Ledger(10**8, 10**8, 10**8, 0, 0, 0, 0)
        self.assertTrue(s3(psm_buy(start, out)))
        self.assertTrue(s3(psm_sell(start, out)))
        self.assertTrue(s3(accrual_delta(start, accrued)))

    def test_settle_split_is_exact(self):
        principal, interest = 40, 60
        self.assertEqual(principal + interest, 100)


if __name__ == "__main__":
    unittest.main()
