import unittest

from hypothesis import given, settings, strategies as st

from model import (
    BPS, E8, amm_fee, amm_out_b2q, amm_out_q2b, amm_value, amm_weight,
    lp_shares,
)


class AmmTest(unittest.TestCase):
    @given(dx=st.integers(0, 10**12), rate=st.integers(0, 10**12),
           fee=st.integers(0, BPS))
    @settings(max_examples=120, deadline=None)
    def test_b2q_output_never_exceeds_gross(self, dx, rate, fee):
        self.assertLessEqual(amm_out_b2q(dx, rate, fee), dx * rate // E8)

    @given(dx=st.integers(0, 10**12), rate=st.integers(1, 10**12),
           fee=st.integers(0, BPS))
    @settings(max_examples=120, deadline=None)
    def test_q2b_output_never_exceeds_gross(self, dx, rate, fee):
        self.assertLessEqual(amm_out_q2b(dx, rate, fee), dx * E8 // rate)

    @given(rb=st.integers(0, 10**12), rq=st.integers(0, 10**12),
           rate=st.integers(0, 10**12))
    @settings(max_examples=80, deadline=None)
    def test_weight_is_bps(self, rb, rq, rate):
        self.assertGreaterEqual(amm_weight(rb, rq, rate), 0)
        self.assertLessEqual(amm_weight(rb, rq, rate), BPS)

    @given(weight=st.integers(0, BPS), base=st.integers(0, 100),
           skew=st.integers(0, 100))
    @settings(max_examples=80, deadline=None)
    def test_fee_is_non_negative(self, weight, base, skew):
        self.assertGreaterEqual(amm_fee(weight, base, skew), 0)

    @given(deposit=st.integers(E8, 10**12), total=st.integers(1, 10**12),
           pool=st.integers(1, 10**12))
    @settings(max_examples=80, deadline=None)
    def test_later_shares_floor(self, deposit, total, pool):
        shares = lp_shares(deposit, total, pool, False)
        self.assertLessEqual(shares * pool, deposit * total)

    @given(rb=st.integers(0, 10**12), rq=st.integers(0, 10**12),
           rate=st.integers(0, 10**12))
    @settings(max_examples=40, deadline=None)
    def test_value_is_non_negative(self, rb, rq, rate):
        self.assertGreaterEqual(amm_value(rb, rq, rate), 0)


if __name__ == "__main__":
    unittest.main()
