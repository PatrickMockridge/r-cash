import unittest

from model import Refused, external_entry, load_mesh


class MeshConfigTest(unittest.TestCase):
    def setUp(self):
        self.mesh = load_mesh()

    def test_default_and_majors_are_enabled(self):
        codes = {c["code"] for c in self.mesh["currencies"]}
        self.assertEqual(self.mesh["defaultCurrency"], "USD")
        self.assertEqual(self.mesh["majorCurrencies"], ["USD", "EUR", "CNY"])
        self.assertTrue(set(self.mesh["majorCurrencies"]) <= codes)

    def test_native_set_and_unordered_pair_count(self):
        codes = [c["code"] for c in self.mesh["currencies"]]
        self.assertEqual(len(codes), 16)
        self.assertEqual(len(set(codes)), 16)
        self.assertEqual(len(codes) * (len(codes) - 1) // 2, 120)

    def test_priority_pairs_are_distinct_and_known(self):
        codes = {c["code"] for c in self.mesh["currencies"]}
        seen = set()
        for pair in self.mesh["priorityPairs"]:
            self.assertNotEqual(pair["base"], pair["quote"])
            self.assertIn(pair["base"], codes)
            self.assertIn(pair["quote"], codes)
            key = tuple(sorted((pair["base"], pair["quote"])))
            self.assertNotIn(key, seen)
            seen.add(key)

    def test_external_assets_require_an_adapter_when_enabled(self):
        for asset in self.mesh["externalAssets"]:
            if asset.get("enabled"):
                self.assertTrue(asset.get("adapterUri"))
            else:
                self.assertIsNone(asset.get("adapterUri"))
            self.assertEqual(asset["kind"], "external")

    def test_external_entry_validation(self):
        entry = external_entry("USDC", "external", "rho:id:adapter", 8, "sponsor")
        self.assertEqual(entry.decimals, 8)
        with self.assertRaises(Refused) as wrong_kind:
            external_entry("USDC", "stablecoin", "rho:id:adapter", 8, "sponsor")
        self.assertEqual(wrong_kind.exception.reason, "external kind")
        with self.assertRaises(Refused) as wrong_decimals:
            external_entry("USDC", "external", "rho:id:adapter", 6, "sponsor")
        self.assertEqual(wrong_decimals.exception.reason, "external decimals")


if __name__ == "__main__":
    unittest.main()
