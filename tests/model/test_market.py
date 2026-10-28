import unittest

from hypothesis import given, settings, strategies as st

from model import Index, Market, Refused, market_for, pause_asset, stage


class MarketTest(unittest.TestCase):
    def test_reverse_lookup_and_reverse_stage_refusal(self):
        pair = Market("NGN/USD:v1", "NGN", "USD", "active", 1)
        index = stage(Index(), pair)
        self.assertEqual(market_for(index, "NGN", "USD"), pair)
        self.assertEqual(market_for(index, "USD", "NGN"), pair)
        with self.assertRaises(Refused) as refused:
            stage(index, Market("USD/NGN:v1", "USD", "NGN", "draft", 1))
        self.assertEqual(refused.exception.reason, "pair active")

    def test_delisted_pair_can_be_replaced_by_higher_version(self):
        index = stage(Index(), Market("NGN/USD:v1", "NGN", "USD", "active", 1))
        index.markets["NGN/USD:v1"] = Market("NGN/USD:v1", "NGN", "USD", "delisted", 1)
        with self.assertRaises(Refused) as refused:
            stage(index, Market("USD/NGN:v1", "USD", "NGN", "draft", 1))
        self.assertEqual(refused.exception.reason, "version")
        newer = stage(index, Market("NGN/USD:v2", "NGN", "USD", "draft", 2))
        self.assertEqual(market_for(newer, "NGN", "USD").market_id, "NGN/USD:v2")

    def test_pause_asset_pauses_every_containing_market_only(self):
        index = Index()
        for market in (
            Market("NGN/USD:v1", "NGN", "USD", "active", 1),
            Market("NGN/ZAR:v1", "NGN", "ZAR", "active", 1),
            Market("EUR/USD:v1", "EUR", "USD", "active", 1),
            Market("ZAR/BWP:v1", "ZAR", "BWP", "draft", 1),
        ):
            index = stage(index, market)
        paused = pause_asset(index, "NGN")
        self.assertEqual(market_for(paused, "NGN", "USD").status, "paused")
        self.assertEqual(market_for(paused, "NGN", "ZAR").status, "paused")
        self.assertEqual(market_for(paused, "EUR", "USD").status, "active")
        self.assertEqual(market_for(paused, "ZAR", "BWP").status, "draft")

    @given(status=st.sampled_from(["active", "paused"]))
    @settings(max_examples=10, deadline=None)
    def test_active_or_paused_is_terminal_for_a_pair(self, status):
        index = stage(Index(), Market("A/B:v1", "A", "B", status, 1))
        with self.assertRaises(Refused):
            stage(index, Market("B/A:v2", "B", "A", "draft", 2))


if __name__ == "__main__":
    unittest.main()
