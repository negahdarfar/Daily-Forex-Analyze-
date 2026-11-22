import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.technical.indicators import analyze
from src.experts.registry import assess_profile
from src.experts.performance import calculate_performance, realized_r_multiple, assess_trader_history

ROOT = Path(__file__).resolve().parents[1]


class ProjectConfigurationTests(unittest.TestCase):
    def test_asset_universe_has_expected_coverage(self):
        assets = json.loads((ROOT / "config/assets.json").read_text(encoding="utf-8"))
        self.assertEqual(len(assets["forex"]), 28)
        self.assertEqual(len(assets["commodities"]), 3)
        self.assertEqual(len(assets["crypto"]), 2)
        self.assertEqual(len(assets["iran_local"]), 3)

    def test_iran_quotes_are_disabled_without_source(self):
        assets = json.loads((ROOT / "config/assets.json").read_text(encoding="utf-8"))
        self.assertTrue(all(not item["enabled"] for item in assets["iran_local"]))

    def test_rss_sources_are_public_and_named(self):
        config = json.loads((ROOT / "config/news_sources.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(config["sources"]), 1)
        self.assertTrue(all(item["url"].startswith("https://") for item in config["sources"]))


class TechnicalAnalysisTests(unittest.TestCase):
    def setUp(self):
        close = np.linspace(100, 150, 120)
        self.frame = pd.DataFrame({
            "Close": close, "High": close + 1.0,
            "Low": close - 1.0, "Volume": np.full(120, 1000)
        })
        self.settings = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))

    def test_indicator_engine_returns_structured_result(self):
        result = analyze(self.frame, self.settings)
        self.assertEqual(result["status"], "ok")
        self.assertIn(result["direction"], {"bullish", "bearish", "neutral"})
        self.assertGreater(result["atr"], 0)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertEqual(result["score_type"], "rule_based_strength_not_probability")

    def test_monotonic_series_has_finite_rsi(self):
        result = analyze(self.frame, self.settings)
        self.assertTrue(np.isfinite(result["rsi14"]))
        self.assertEqual(result["rsi14"], 100.0)


    def test_realized_r_multiple_supports_long_and_short(self):
        self.assertEqual(realized_r_multiple("long", 100, 95, 110), 2.0)
        self.assertEqual(realized_r_multiple("short", 100, 105, 90), 2.0)

    def test_performance_metrics_calculate_expectancy_and_drawdown(self):
        metrics = calculate_performance([1.0, -1.0, 2.0, 1.0], minimum_sample=4)
        self.assertEqual(metrics["sample_size"], 4)
        self.assertAlmostEqual(metrics["expectancy_r"], 0.75)
        self.assertEqual(metrics["status"], "measured")
        self.assertTrue(metrics["ranking_eligible"])

    def test_unverified_trades_are_excluded(self):
        metrics = assess_trader_history([
            {"realized_r": 5, "verification_status": "claimed"},
            {"realized_r": 1, "verification_status": "independently_verified"}
        ], minimum_sample=1)
        self.assertEqual(metrics["sample_size"], 1)
        self.assertEqual(metrics["excluded_unverified_count"], 1)

    def test_forecast_profile_without_evidence_is_unverified(self):
        result = assess_profile({"name": "Example"})
        self.assertEqual(result["status"], "unverified")
        self.assertGreater(len(result["missing_evidence"]), 0)


if __name__ == "__main__":
    unittest.main()
