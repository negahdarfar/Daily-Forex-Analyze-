import unittest

from src.analysis.market_intelligence import build_market_intelligence


class MarketIntelligenceTests(unittest.TestCase):
    def test_empty_inputs_are_safe_and_explicit(self):
        result = build_market_intelligence([], [], [], [])
        self.assertEqual(result["coverage"]["fresh_fx_pairs_with_direction"], 0)
        self.assertEqual(len(result["currency_strength"]), 8)
        self.assertTrue(all(row["status"] == "insufficient_evidence" for row in result["currency_strength"]))
        self.assertEqual(result["pair_confluence"], [])

    def test_pair_strength_uses_technical_direction_and_fresh_data(self):
        rows = [
            {"asset": "EURUSD", "status": "available", "market_timestamp": "2026-11-22T00:00:00+00:00",
             "analysis": {"status": "ok", "direction": "bullish", "score": 80}},
            {"asset": "GBPUSD", "status": "available", "market_timestamp": "2026-11-22T00:00:00+00:00",
             "analysis": {"status": "ok", "direction": "bullish", "score": 70}},
            {"asset": "USDJPY", "status": "stale",
             "analysis": {"status": "ok", "direction": "bullish", "score": 99}},
        ]
        result = build_market_intelligence(rows, [], [], [])
        by_code = {row["currency"]: row for row in result["currency_strength"]}
        self.assertGreater(by_code["EUR"]["technical_score"], by_code["USD"]["technical_score"])
        self.assertEqual(result["coverage"]["fresh_fx_pairs_with_direction"], 2)
        self.assertEqual(result["coverage"]["stale_fx_pairs"], 1)

    def test_cot_requires_minimum_history(self):
        macro = [{"source": "CFTC", "status": "available", "observations": [
            {"contract": "Euro FX", "net_position_52w_zscore": 1.2, "history_weeks": 30, "report_date": "2026-11-17"},
            {"contract": "British Pound", "net_position_52w_zscore": -1.0, "history_weeks": 12, "report_date": "2026-11-17"},
        ]}]
        result = build_market_intelligence([], [], macro, [])
        by_code = {row["currency"]: row for row in result["currency_strength"]}
        self.assertIsNotNone(by_code["EUR"]["cot_score"])
        self.assertIsNone(by_code["GBP"]["cot_score"])


if __name__ == "__main__":
    unittest.main()
