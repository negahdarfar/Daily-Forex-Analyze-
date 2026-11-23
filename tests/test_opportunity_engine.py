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

    def test_unknown_cost_never_becomes_zero_net_cost_or_active(self):
        def make_frame(periods, freq, hourly_trigger=False):
            idx = pd.date_range("2026-01-01T00:00:00Z", periods=periods, freq=freq)
            t = np.arange(periods)
            close = 100 + 0.12 * t + 2 * np.sin(t / 6)
            frame = pd.DataFrame({
                "Open": close - 0.15, "High": close + 0.5,
                "Low": close - 0.5, "Close": close, "Volume": 100,
            }, index=idx)
            if hourly_trigger:
                ema = frame["Close"].ewm(span=20, adjust=False).mean()
                for i in range(periods - 4, periods - 1):
                    frame.iloc[i, frame.columns.get_loc("Low")] = float(ema.iloc[i]) - 0.25
                frame.iloc[-1, frame.columns.get_loc("Open")] = float(frame["Close"].iloc[-1]) - 0.2
            return frame

        frames = {
            "1d": make_frame(140, "D"),
            "4h": make_frame(140, "4h"),
            "1h": make_frame(140, "h", hourly_trigger=True),
        }
        settings = {
            "technical": {"minimum_history_rows": 60, "ema_fast": 20, "ema_slow": 50,
                          "rsi_period": 14, "atr_period": 14, "stop_atr_multiple": 1.5},
            "risk": {"minimum_net_rr": 2.0, "stop_atr_buffer": 0.2},
            "ranking": {"weights": {"technical": 25, "net_rr": 20, "fundamental": 15,
                                    "news": 10, "data_quality": 15,
                                    "independent_evidence": 10, "liquidity": 5}},
        }
        result = build_opportunity("EURUSD", frames, settings)
        if result["setup_type"] is not None and result["gross_rr"] is not None:
            self.assertIsNone(result["net_rr"])
            self.assertNotEqual(result["status"], "active")
            self.assertIn("instrument_specific_round_trip_cost_not_configured", result["missing_evidence"])

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
