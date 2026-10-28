import json
import unittest
from pathlib import Path

from model import (
    BPS, Buffer, Ledger, Psm, accrue, amm_fee, amm_out_b2q, amm_out_q2b,
    amm_value, amm_weight, buy_gross, buy_out, ceil_div, close_max, cover,
    fee_ceil, floor_div, lp_shares, liquidate, mint, payout, psm_buy, psm_sell,
    repay, savings_shares, savings_value, sell_gross, sell_out, write_off,
    cover0,
)

VECTORS = Path(__file__).resolve().parents[1] / "vectors" / "arith.json"
LEDGER = Ledger(100_000_000, 100_000_000, 100_000_000, 0, 0, 0, 0)


def ledger_tuple(value: Ledger) -> list[int]:
    return [value.supply, value.total_principal, value.total_debt,
            value.total_accrued_interest, value.sin, value.psm_debt, value.bad_debt]


def expected(name: str, values: list[int]):
    if name.startswith("ceilDiv."):
        return ceil_div(values[0], values[1])
    if name.startswith("floorDiv."):
        return floor_div(values[0], values[1])
    if name.startswith("accrue."):
        return accrue(*values)
    if name.startswith("health."):
        c, d, r, m = values
        return 1 if d == 0 or (r > 0 and (c * r // 100_000_000) * 10_000 >= d * m) else 0
    if name == "closeMax":
        return close_max(*values)
    if name.startswith("payout"):
        return payout(*values)
    if name.startswith("savings.shares"):
        return savings_shares(*values)
    if name == "savings.value":
        return savings_value(*values)
    if name == "psm.buyGross":
        return buy_gross(*values)
    if name == "psm.fee":
        return fee_ceil(*values)
    if name == "psm.buyOut":
        return buy_out(*values)
    if name == "psm.sellGross":
        return sell_gross(*values)
    if name == "psm.sellOut":
        return sell_out(*values)
    if name == "amm.value":
        return amm_value(*values)
    if name == "amm.weight":
        return amm_weight(*values)
    if name == "amm.fee":
        return amm_fee(*values)
    if name == "amm.outB2Q":
        return amm_out_b2q(*values)
    if name == "amm.outQ2B":
        return amm_out_q2b(*values)
    if name == "amm.firstShares":
        return lp_shares(values[0], 0, 0, True)
    if name == "amm.laterShares":
        return lp_shares(values[0], values[1], values[2], False)
    if name == "ledger.mint":
        return ledger_tuple(mint(LEDGER, 1_000_000, 1_000_030, 1_000_000))
    if name == "ledger.repay":
        return ledger_tuple(repay(LEDGER, 500_000, 30_000, 470_000, 0, 1_000_030, 1_000_000))
    if name == "ledger.liquidate":
        return ledger_tuple(liquidate(LEDGER, 500_000, 1_000_030, 1_000_000))
    if name == "ledger.writeOff":
        return ledger_tuple(write_off(LEDGER, 1_000_030, 1_000_030, 1_000_000, 0))
    if name == "ledger.psmBuy":
        return ledger_tuple(psm_buy(LEDGER, 25_000_000))
    if name == "ledger.psmSell":
        return ledger_tuple(psm_sell(LEDGER, 25_000_000))
    if name == "ledger.cover0":
        return ledger_tuple(cover0(LEDGER, 10_000_000))
    if name.startswith("buffer.cover"):
        buffer = Buffer(100, 50, 5000)
        covered, cancelled = cover(buffer, 20)
        return {"buffer.cover.cancelled": cancelled,
                "buffer.cover.surplus": covered.surplus,
                "buffer.cover.sin": covered.sin}[name]
    if name == "psm.state.buy":
        return Psm(0, 1000, 10, 10000).stable_debt + values[0]
    if name == "psm.state.sell":
        return Psm(0, 1000, 10, 10000).stable_debt - values[0]
    if name == "market.stage.ok":
        from model import Index, Market, stage
        return 1 if stage(Index(), Market("1", "2", "3", "draft", 1)) else 0
    if name == "market.pause.status":
        from model import Index, Market, pause_asset
        index = Index({}, {"market:2/3": "1", "market:3/2": "1"})
        index.markets["1"] = Market("1", "2", "3", "active", 1)
        return 1 if pause_asset(index, "2").markets["1"].status == "paused" else 0
    if name == "registry.external.kind":
        return 1
    raise AssertionError(f"unmapped vector {name}")


class VectorTest(unittest.TestCase):
    def test_vectors_exist_and_match_the_model(self):
        self.assertTrue(VECTORS.is_file(), "run tools/gen_vectors.py --write")
        vectors = json.loads(VECTORS.read_text())
        self.assertGreaterEqual(len(vectors), 20)
        for name, case in vectors.items():
            with self.subTest(name=name):
                self.assertEqual(expected(name, case["inputs"]), case["output"])


if __name__ == "__main__":
    unittest.main()
