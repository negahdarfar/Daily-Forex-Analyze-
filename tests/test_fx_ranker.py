import unittest
from datetime import datetime, timedelta, timezone

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
        self.assertEqual(item["fundamental_status"], "policy_rate_data_missing_or_stale")
        self.assertIsNone(item["score_components"]["fundamental"])
        self.assertLess(item["score_coverage_pct"], 100.0)
        self.assertEqual(item["calendar_status"], "us_calendar_unavailable_unknown")
        self.assertIn("paired_policy_rate_data_missing_or_stale", item["missing_evidence"])
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

    def test_policy_rate_carry_and_90d_impulse_are_directional(self):
        policy_rates = {"status": "available", "rates": {
            "EUR": {"status": "available", "policy_rate_pct": 4.0, "change_90d_pp": 0.5},
            "USD": {"status": "available", "policy_rate_pct": 2.0, "change_90d_pp": -0.25},
        }}
        bullish = rank_fx_pairs([row("EURUSD", "bullish")], policy_rates=policy_rates)["opportunities"][0]
        bearish = rank_fx_pairs([row("EURUSD", "bearish")], policy_rates=policy_rates)["opportunities"][0]
        self.assertGreater(bullish["score_components"]["fundamental"], 50)
        self.assertLess(bearish["score_components"]["fundamental"], 50)
        self.assertEqual(bullish["fundamental_status"], "policy_rate_carry_and_90d_change_proxy")
        self.assertIn("inflation_growth_labor_and_market_consensus_surprise_not_integrated", bullish["missing_evidence"])

    def test_us_calendar_blackout_is_flagged_and_non_us_coverage_stays_unknown(self):
        event_time = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        calendar = {
            "status": "available",
            "events": [{"scheduled_at_utc": event_time, "name": "FOMC", "importance": "high"}],
        }
        usd_pair = rank_fx_pairs([row("EURUSD")], economic_calendar=calendar)["opportunities"][0]
        non_us_pair = rank_fx_pairs([row("EURJPY")], economic_calendar=calendar)["opportunities"][0]
        self.assertEqual(usd_pair["calendar_status"], "high_impact_us_event_blackout")
        self.assertEqual(usd_pair["score_components"]["calendar_risk"], 0.0)
        self.assertIn("high_impact_us_event_blackout_window", usd_pair["missing_evidence"])
        self.assertEqual(non_us_pair["calendar_status"], "non_us_currency_calendar_not_covered")
        self.assertIsNone(non_us_pair["score_components"]["calendar_risk"])

    def test_stale_us_calendar_never_clears_event_risk(self):
        result = rank_fx_pairs([row("EURUSD")], economic_calendar={
            "status": "stale", "events": []
        })
        item = result["opportunities"][0]
        self.assertEqual(item["calendar_status"], "stale_us_calendar_unknown")
        self.assertIsNone(item["score_components"]["calendar_risk"])
        self.assertIn("fresh_us_economic_calendar_required", item["missing_evidence"])

    def test_expert_consensus_requires_two_independent_publishers(self):
        result = rank_fx_pairs(
            [row("EURUSD")],
            directional_evidence={"EURUSD": {
                "net_bias": 0.8, "bullish_publishers": 1, "bearish_publishers": 0
            }},
        )
        item = result["opportunities"][0]
        self.assertIsNone(item["score_components"]["expert_consensus"])
        self.assertIn("two_or_more_independent_forex_analysis_publishers", item["missing_evidence"])

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
