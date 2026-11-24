import unittest
import pandas as pd
from src.analysis.currency_strength import calculate_currency_strength
from src.analysis.data_quality import age_status, validate_ohlc
from src.analysis.macro_surprise import standardized_surprise
from src.analysis.news_sentiment import score_headline, deduplicate_headlines
from src.analysis.walk_forward import evaluate_signals
from src.analysis.market_structure import analyze_market_structure
from src.analysis.consensus import build_consensus


class IntelligenceV2Tests(unittest.TestCase):
    def test_currency_strength_is_relative_and_coverage_aware(self):
        idx = pd.date_range("2025-01-01", periods=25, tz="UTC")
        data = {"EURUSD": pd.Series(range(100, 125), index=idx),
                "GBPUSD": pd.Series(range(100, 125), index=idx)}
        result = calculate_currency_strength(data, lookback=10, min_pairs_per_currency=1)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["currencies"]["JPY"]["status"], "insufficient_pair_coverage")

    def test_macro_requires_history_for_zscore(self):
        self.assertIsNone(standardized_surprise(3, 2, [1, 2])["z_score"])
        self.assertEqual(standardized_surprise(3, 2)["surprise"], 1)

    def test_negation_and_headline_dedup(self):
        self.assertEqual(score_headline("USD not strong")["label"], "negative")
        self.assertEqual(len(deduplicate_headlines([{"title":"Rate rises!"},{"title":"Rate rises!"}])), 1)

    def test_ohlc_validation_and_age(self):
        idx = pd.date_range("2025-01-01", periods=2, tz="UTC")
        frame = pd.DataFrame({"Open":[1,1],"High":[2,2],"Low":[.5,.5],"Close":[1.5,1.5]}, index=idx)
        self.assertEqual(validate_ohlc(frame)["status"], "available")
        self.assertEqual(age_status("2025-01-01T00:00:00Z", 10, now=pd.Timestamp("2025-01-01T00:05:00Z").to_pydatetime())["status"], "fresh")

    def test_consensus_excludes_stale_and_unverified_domains(self):
        evidence = {
            "technical": {"score": 80, "verified": True, "fresh": True, "source": "unit-test"},
            "macro": {"score": 20, "verified": True, "fresh": False},
            "news": {"score": 10, "verified": False, "fresh": True},
        }
        result = build_consensus(evidence, weights={"technical": 1, "macro": 1, "news": 1}, minimum_coverage_pct=30)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["score"], 80)
        self.assertEqual(result["coverage_pct"], 33.3)

    def test_market_structure_reports_confirmed_only_events(self):
        idx = pd.date_range("2025-01-01", periods=40, freq="h", tz="UTC")
        close = [100 + (i % 7) for i in range(40)]
        frame = pd.DataFrame({
            "Open": close,
            "High": [x + 1 for x in close],
            "Low": [x - 1 for x in close],
            "Close": close,
        }, index=idx)
        result = analyze_market_structure(frame, left=2, right=2)
        self.assertEqual(result["status"], "available")
        self.assertTrue(any("confirmed_at" in event for event in result["events"] if event["type"].startswith("swing_")) )

    def test_walk_forward_uses_future_observation(self):
        t = pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC")
        signals = pd.DataFrame({"signal":[1,-1], "signal_time":[t[0],t[2]]})
        returns = pd.Series([.01,-.02,.03,.01], index=t)
        result = evaluate_signals(signals, returns, min_trades=2)
        self.assertEqual(result["trade_count"], 2)
        self.assertAlmostEqual(result["expectancy_per_trade"], -.015)


    def test_fx_ranker_integrates_relative_strength_and_consensus(self):
        from src.analysis.fx_ranker import rank_fx_pairs
        results = [{"asset": "EURUSD", "status": "available", "age_hours": 1,
                    "market_timestamp": "2025-01-01T00:00:00Z",
                    "analysis": {"status": "ok", "direction": "bullish", "score": 75,
                                 "close": 1.1, "rsi14": 55, "adx": 22, "atr_pct": 0.4}}]
        candidate = {"symbol": "EURUSD", "timeframes": {
            "1d": {"status": "ok", "direction": "bullish", "score": 70},
            "4h": {"status": "ok", "direction": "bullish", "score": 72},
            "1h": {"status": "ok", "direction": "bullish", "score": 75}},
            "market_structure": {"status": "available", "events": [
                {"type": "BOS", "direction": "bullish", "at": pd.Timestamp.now(tz="UTC").isoformat()},
                {"type": "bullish_FVG", "at": pd.Timestamp.now(tz="UTC").isoformat()}]}}
        strength = {"status": "available", "currencies": {
            "EUR": {"status": "available", "relative_score": 80},
            "USD": {"status": "available", "relative_score": 40}}}
        result = rank_fx_pairs(results, opportunity_candidates=[candidate],
            currency_strength=strength,
            policy={"weights": {"technical": 50, "currency_strength": 50}})
        self.assertEqual(result["ranked_count"], 1)
        row = result["opportunities"][0]
        self.assertGreater(row["score_components"]["currency_strength"], 50)
        self.assertEqual(row["score_components"]["market_structure"], 90.0)
        self.assertEqual(row["consensus"]["status"], "available")
        self.assertTrue(result["coverage"]["relative_currency_strength_integrated"])

if __name__ == "__main__":
    unittest.main()
