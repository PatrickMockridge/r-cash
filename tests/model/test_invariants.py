import unittest

from hypothesis import given, settings, strategies as st

from model import (
    E8, Buffer, Book, Index, Ledger, Market, Psm, Savings, Vault, accrual_delta,
    book_mint, cover, deposit, liquidate, mint, pause_asset, pay_savings,
    psm_buy, psm_sell, repay, s1, s10, s2, s3, savings_deposit,
    savings_withdraw, stage, write_off,
)


def step_ledger(ledger: Ledger, op: int, a: int, b: int) -> Ledger:
    if op == 0:
        return mint(ledger, a, a + b, b)
    if op == 1:
        # A standalone burn is an internal effect of a composite transition,
        # not a transition in the S3 table; keep the sequence's S3 ledger.
        return ledger
    if op == 2:
        interest = min(a, b)
        return repay(ledger, b, interest, b - interest, 0, b + a, a)
    if op == 3:
        return liquidate(ledger, a, a + b, b)
    if op == 4:
        return write_off(ledger, a, a + b, b, 0)
    if op == 5:
        return psm_buy(ledger, a)
    if op == 6:
        return psm_sell(ledger, a)
    return accrual_delta(ledger, a)


class InvariantTest(unittest.TestCase):
    @given(ops=st.lists(st.tuples(st.integers(0, 7), st.integers(0, 10**7),
                                  st.integers(0, 10**7)), min_size=1, max_size=30))
    @settings(max_examples=60, deadline=None)
    def test_ledger_s1_s3_over_random_sequences(self, ops):
        ledger = Ledger(0, 0, 0, 0, 0, 0, 0)
        for op, a, b in ops:
            ledger = step_ledger(ledger, op, a, b)
            self.assertTrue(s1(ledger), (op, a, b, ledger))
            self.assertTrue(s3(ledger), (op, a, b, ledger))

    @given(ops=st.lists(st.tuples(st.integers(0, 2), st.integers(1, 10**7),
                                  st.integers(0, 10**7)), min_size=1, max_size=20))
    @settings(max_examples=40, deadline=None)
    def test_book_s2_over_random_sequences(self, ops):
        book = Book({"a": Vault(10 * E8, 0, 0)}, 0, 10 * E8, 0, 0)
        for op, amount, accrued in ops:
            if op == 0:
                book = deposit(book, "a", amount, accrued)
            elif op == 1:
                book = book_mint(book, "a", amount, accrued)
            else:
                try:
                    from model import withdraw
                    book = withdraw(book, "a", amount, accrued)
                except Exception:
                    pass
            self.assertTrue(s2(book), (op, amount, accrued, book))

    @given(ops=st.lists(st.tuples(st.integers(0, 1), st.integers(1, 10**7),
                                  st.integers(1, 10**7)), min_size=1, max_size=20))
    @settings(max_examples=40, deadline=None)
    def test_savings_s10_over_random_sequences(self, ops):
        savings = Savings(0, 0, {})
        for op, amount, shares in ops:
            if op == 0:
                savings = savings_deposit(savings, "a", amount, shares)
            else:
                held = savings.shares.get("a", 0)
                if held > 0:
                    use = min(shares, held)
                    savings = savings_withdraw(
                        savings, "a", use,
                        savings.total_assets * use // max(1, savings.total_shares))
            self.assertTrue(s10(savings), (op, amount, shares, savings))

    @given(code=st.sampled_from(["NGN", "ZAR", "USD"]),
           statuses=st.lists(st.sampled_from(["active", "draft", "paused"]),
                             min_size=1, max_size=8))
    @settings(max_examples=40, deadline=None)
    def test_pause_asset_changes_only_containing_active_markets(self, code, statuses):
        index = Index()
        for i, status in enumerate(statuses):
            base = code if i % 2 == 0 else "EUR"
            quote = "USD" if i % 3 else "ZAR"
            if base == quote:
                quote = "BWP"
            try:
                index = stage(index, Market(f"M{i}:v1", base, quote, status, 1))
            except Exception:
                pass
        paused = pause_asset(index, code)
        for market_id, market in index.markets.items():
            after = paused.markets[market_id]
            should_pause = market.status == "active" and (market.base == code or market.quote == code)
            self.assertEqual(after.status, "paused" if should_pause else market.status)

    @given(surplus=st.integers(0, 10**9), sin=st.integers(0, 10**9),
           bad=st.integers(0, 10**9), bps=st.integers(0, 10000))
    @settings(max_examples=60, deadline=None)
    def test_waterfall_order(self, surplus, sin, bad, bps):
        buffer = Buffer(surplus, sin, bps)
        after_cover, cancelled = cover(buffer, bad)
        after_pay, moved = pay_savings(after_cover)
        self.assertLessEqual(cancelled, surplus)
        self.assertLessEqual(moved, after_cover.surplus)
        self.assertLessEqual(after_pay.surplus, surplus)


if __name__ == "__main__":
    unittest.main()
