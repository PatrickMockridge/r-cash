import unittest

from hypothesis import given, settings, strategies as st

from model import (
    E8, Book, Refused, Vault, book_mint, deposit, health, s2, withdraw,
)


class VaultTest(unittest.TestCase):
    def setUp(self):
        self.book = Book({"alice": Vault(10 * E8, 3 * E8, 0)}, 3 * E8, 10 * E8, 0, 0)
        self.assertTrue(s2(self.book))

    @given(amount=st.integers(1, 10**8), accrued=st.integers(0, 10**9))
    @settings(max_examples=80, deadline=None)
    def test_deposit_preserves_s2(self, amount, accrued):
        accrued = max(accrued, self.book.vaults["alice"].debt)
        self.assertTrue(s2(deposit(self.book, "alice", amount, accrued)))

    @given(amount=st.integers(1, 10**8), accrued=st.integers(0, 10**9))
    @settings(max_examples=80, deadline=None)
    def test_mint_preserves_s2(self, amount, accrued):
        accrued = max(accrued, self.book.vaults["alice"].debt)
        self.assertTrue(s2(book_mint(self.book, "alice", amount, accrued)))

    @given(amount=st.integers(1, 10**8), accrued=st.integers(0, 10**9))
    @settings(max_examples=80, deadline=None)
    def test_withdraw_preserves_s2_or_refuses(self, amount, accrued):
        accrued = max(accrued, self.book.vaults["alice"].debt)
        try:
            out = withdraw(self.book, "alice", amount, accrued)
        except Refused as error:
            self.assertEqual(error.reason, "amount")
            self.assertGreater(amount, self.book.vaults["alice"].collateral)
        else:
            self.assertTrue(s2(out))

    @given(collateral=st.integers(0, 10**10), debt=st.integers(0, 10**9),
           rate=st.integers(0, 10**9), mcr=st.integers(1, 50000))
    @settings(max_examples=120, deadline=None)
    def test_health_matches_formula(self, collateral, debt, rate, mcr):
        expected = debt == 0 or (rate > 0 and ((collateral * rate) // E8) * 10000 >= debt * mcr)
        self.assertEqual(health(collateral, debt, rate, mcr), expected)


if __name__ == "__main__":
    unittest.main()
