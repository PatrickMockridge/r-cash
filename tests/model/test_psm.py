import unittest

from hypothesis import given, settings, strategies as st

from model import (
    BPS, Psm, Refused, buy_gross, buy_out, fee_ceil, psm_buy_state,
    psm_sell_state, sell_gross, sell_out,
)


class PsmTest(unittest.TestCase):
    @given(gross=st.integers(0, 10**12), bps=st.integers(0, BPS))
    @settings(max_examples=100, deadline=None)
    def test_fee_never_exceeds_gross(self, gross, bps):
        self.assertLessEqual(fee_ceil(gross, bps), gross)

    @given(amount=st.integers(1, 10**10), rate=st.integers(1, 10**12),
           bps=st.integers(0, BPS))
    @settings(max_examples=100, deadline=None)
    def test_buy_output_is_gross_minus_fee(self, amount, rate, bps):
        gross = buy_gross(amount, rate)
        self.assertEqual(buy_out(amount, rate, bps), gross - fee_ceil(gross, bps))

    @given(amount=st.integers(1, 10**10), rate=st.integers(1, 10**12),
           bps=st.integers(0, BPS))
    @settings(max_examples=100, deadline=None)
    def test_sell_output_is_gross_minus_fee(self, amount, rate, bps):
        gross = sell_gross(amount, rate)
        self.assertEqual(sell_out(amount, rate, bps), gross - fee_ceil(gross, bps))

    def test_ceiling_and_floor_refusals(self):
        p = Psm(0, 100, 10, 1000)
        with self.assertRaises(Refused) as ceiling:
            psm_buy_state(p, 101)
        self.assertEqual(ceiling.exception.reason, "ceiling")
        with self.assertRaises(Refused) as floor:
            psm_sell_state(p, 1001)
        self.assertEqual(floor.exception.reason, "psm floor")


if __name__ == "__main__":
    unittest.main()
