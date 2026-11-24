import unittest
import pandas as pd
from src.analysis.currency_strength import calculate_currency_strength
from src.analysis.data_quality import age_status, validate_ohlc
from src.analysis.macro_surprise import standardized_surprise
from src.analysis.news_sentiment import score_headline, deduplicate_headlines
from src.analysis.walk_forward import evaluate_signals


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

    def test_walk_forward_uses_future_observation(self):
        t = pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC")
        signals = pd.DataFrame({"signal":[1,-1], "signal_time":[t[0],t[2]]})
        returns = pd.Series([.01,-.02,.03,.01], index=t)
        result = evaluate_signals(signals, returns, min_trades=2)
        self.assertEqual(result["trade_count"], 2)
        self.assertAlmostEqual(result["expectancy_per_trade"], -.015)


if __name__ == "__main__":
    unittest.main()
