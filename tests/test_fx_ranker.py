import unittest

from src.analysis.fx_ranker import rank_fx_pairs


def row(symbol, direction="bullish", score=70, age=3, status="available"):
    return {
        "asset": symbol,
        "status": status,
        "age_hours": age,
        "market_timestamp": "2026-11-24T08:00:00+00:00",
        "analysis": {"status": "ok", "direction": direction, "score": score,
                     "close": 1.1, "rsi14": 55, "adx": 24, "atr_pct": 0.5},
    }


class FxRankerTests(unittest.TestCase):
    def test_returns_at_most_ten_fx_pairs_and_excludes_non_fx_assets(self):
        pairs = [
            "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDJPY", "USDCHF", "USDCAD",
            "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "EURNZD", "GBPJPY",
            "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD", "AUDJPY", "AUDNZD", "AUDCAD",
            "AUDCHF", "NZDJPY", "NZDCAD", "NZDCHF", "CADJPY", "CADCHF", "CHFJPY",
        ]
        results = [row(pair, score=60 + index) for index, pair in enumerate(pairs)]
        results += [row("XAUUSD", score=99), row("BTCUSD", score=99)]
        result = rank_fx_pairs(results)
        self.assertEqual(result["eligible_directional_pairs"], 28)
        self.assertEqual(result["ranked_count"], 10)
        self.assertTrue(all(len(item["symbol"]) == 6 and item["symbol"] in pairs for item in result["opportunities"]))

    def test_stale_unavailable_and_neutral_pairs_are_excluded(self):
        results = [
            row("EURUSD", age=80),
            row("GBPUSD", status="unavailable"),
            row("AUDUSD", direction="neutral"),
            row("NZDUSD", age=2),
        ]
        result = rank_fx_pairs(results, max_age_hours=36)
        self.assertEqual([item["symbol"] for item in result["opportunities"]], ["NZDUSD"])
        self.assertEqual(result["excluded"]["stale"], 1)
        self.assertEqual(result["excluded"]["unavailable"], 1)
        self.assertEqual(result["excluded"]["neutral"], 1)

    def test_missing_macro_and_calendar_are_never_fabricated(self):
        result = rank_fx_pairs([row("EURUSD")])
        item = result["opportunities"][0]
        self.assertEqual(item["fundamental_status"], "not_integrated")
        self.assertEqual(item["calendar_status"], "not_connected")
        self.assertIn("fundamental_rate_path_and_comparable_macro_surprise", item["missing_evidence"])
        self.assertIn("timestamped_economic_calendar_and_event_blackout", item["missing_evidence"])
        self.assertFalse(result["coverage"]["fundamental_integrated"])
        self.assertFalse(result["coverage"]["economic_calendar_connected"])

    def test_cot_and_news_scores_are_directional_for_pair(self):
        intelligence = {"currency_strength": [
            {"currency": "EUR", "cot_score": 80, "news_score": 60},
            {"currency": "USD", "cot_score": -40, "news_score": -20},
        ]}
        bullish = rank_fx_pairs([row("EURUSD", "bullish")], intelligence)["opportunities"][0]
        bearish = rank_fx_pairs([row("EURUSD", "bearish")], intelligence)["opportunities"][0]
        self.assertGreater(bullish["score_components"]["cot_positioning"], 50)
        self.assertLess(bearish["score_components"]["cot_positioning"], 50)
        self.assertGreater(bullish["score_components"]["news"], 50)
        self.assertLess(bearish["score_components"]["news"], 50)

    def test_expert_consensus_requires_two_independent_publishers(self):
        result = rank_fx_pairs(
            [row("EURUSD")],
            directional_evidence={"EURUSD": {
                "net_bias": 0.8, "bullish_publishers": 1, "bearish_publishers": 0
            }},
        )
        item = result["opportunities"][0]
        self.assertIsNone(item["score_components"]["expert_consensus"])
        self.assertIn("two_or_more_independent_expert_publishers", item["missing_evidence"])

        confirmed = rank_fx_pairs(
            [row("EURUSD")],
            directional_evidence={"EURUSD": {
                "net_bias": 0.8, "bullish_publishers": 2, "bearish_publishers": 0
            }},
        )["opportunities"][0]
        self.assertEqual(confirmed["expert_publishers"], 2)
        self.assertGreater(confirmed["score_components"]["expert_consensus"], 50)


if __name__ == "__main__":
    unittest.main()
