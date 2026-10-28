import unittest

from model import (
    E8, Index, Market, Psm, Refused, Savings, Vault, Book, external_entry,
    psm_buy_state, psm_sell_state, savings_withdraw, stage, withdraw,
)


class RefusalTest(unittest.TestCase):
    def assert_refused(self, reason, fn, *args):
        with self.assertRaises(Refused) as caught:
            fn(*args)
        self.assertEqual(caught.exception.reason, reason)

    def test_market_pair_refusals(self):
        index = stage(Index(), Market("NGN/USD:v1", "NGN", "USD", "active", 1))
        self.assert_refused("pair active", stage, index,
                            Market("USD/NGN:v1", "USD", "NGN", "draft", 1))

    def test_external_asset_refusals(self):
        self.assert_refused("external kind", external_entry,
                            "USDC", "stablecoin", "rho:id:a", 8, "sponsor")
        self.assert_refused("external decimals", external_entry,
                            "USDC", "external", "rho:id:a", 6, "sponsor")
        self.assert_refused("external attestation", external_entry,
                            "USDC", "external", "", 8, "sponsor")

    def test_psm_refusals(self):
        self.assert_refused("ceiling", psm_buy_state, Psm(0, 10, 10, 1000), 11)
        self.assert_refused("psm floor", psm_sell_state, Psm(0, 10, 10, 1000), 1001)

    def test_vault_and_savings_refusals(self):
        book = Book({"a": Vault(10, 0, 0)}, 0, 10, 0, 0)
        self.assert_refused("amount", withdraw, book, "a", 11, 0)
        self.assert_refused("shares", savings_withdraw, Savings(10, 10, {"a": 1}), "a", 2, 0)


if __name__ == "__main__":
    unittest.main()
