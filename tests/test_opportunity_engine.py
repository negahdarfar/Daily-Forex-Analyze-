import unittest
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.analysis.opportunity_engine import resample_completed_4h, rank_opportunities, build_opportunity


class MultiTimeframeDataTests(unittest.TestCase):
    def test_resample_excludes_incomplete_hour_and_four_hour_bucket(self):
        index = pd.date_range("2026-11-23T00:00:00Z", periods=12, freq="h")
        close = np.arange(100.0, 112.0)
        frame = pd.DataFrame({
            "Open": close - 0.2, "High": close + 0.5,
            "Low": close - 0.5, "Close": close, "Volume": 10,
        }, index=index)
        result = resample_completed_4h(frame, datetime.fromisoformat("2026-11-23T11:30:00+00:00"))
        self.assertEqual(len(result), 2)
        self.assertEqual(list(result.index), [
            pd.Timestamp("2026-11-23T04:00:00Z"),
            pd.Timestamp("2026-11-23T08:00:00Z"),
        ])
        self.assertEqual(result.iloc[0]["Volume"], 40)

    def test_resample_requires_four_complete_hourly_bars(self):
        index = pd.date_range("2026-11-23T00:00:00Z", periods=12, freq="h")
        close = np.arange(100.0, 112.0)
        frame = pd.DataFrame({
            "Open": close, "High": close + 1, "Low": close - 1,
            "Close": close,
        }, index=index)
        result = resample_completed_4h(frame, datetime.fromisoformat("2026-11-23T12:30:00+00:00"))
        self.assertEqual(len(result), 3)
        self.assertTrue((result.index <= pd.Timestamp("2026-11-23T12:30:00Z")).all())


class OpportunityRankingTests(unittest.TestCase):
    def test_missing_timeframe_data_is_unrankable_not_neutral(self):
        settings = {"technical": {"minimum_history_rows": 60}}
        result = build_opportunity("EURUSD", {"1d": pd.DataFrame(), "4h": pd.DataFrame(), "1h": pd.DataFrame()}, settings)
        self.assertEqual(result["status"], "unrankable")
        self.assertIn("insufficient_or_invalid_ohlc_for_1d_4h_1h", result["missing_evidence"])

    def test_ranking_never_fills_ten_with_watchlist_or_conditional(self):
        rows = [
            {"symbol": "EURUSD", "status": "active", "score_adjusted": 91},
            {"symbol": "GBPUSD", "status": "conditional", "score_adjusted": 99},
            {"symbol": "USDJPY", "status": "watchlist", "score_adjusted": 100},
        ]
        result = rank_opportunities(rows, max_items=10)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["opportunities"][0]["symbol"], "EURUSD")
        self.assertEqual(result["conditional_count"], 1)
        self.assertEqual(result["watchlist_count"], 1)

    def test_ranking_cap_is_hard_limited_to_ten(self):
        rows = [{"symbol": f"PAIR{i}", "status": "active", "score_adjusted": 80-i} for i in range(15)]
        result = rank_opportunities(rows, max_items=50)
        self.assertEqual(result["count"], 10)


if __name__ == "__main__":
    unittest.main()
