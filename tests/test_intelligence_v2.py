import unittest
import pandas as pd
from src.analysis.currency_strength import calculate_currency_strength
from src.analysis.data_quality import age_status, validate_ohlc
from src.analysis.macro_surprise import standardized_surprise
from src.analysis.news_sentiment import score_headline, deduplicate_headlines
from src.analysis.walk_forward import evaluate_signals
from src.analysis.market_structure import analyze_market_structure
from src.analysis.consensus import build_consensus
from src.data.global_economic_calendar import fetch_global_economic_calendar, _numeric
from src.analysis.ohlc_backtest import backtest_ohlc_signals
from src.analysis.ecb_crosscheck import build_ecb_fx_cross_checks
from src.experts.verified_ledger import build_verified_expert_evidence, validate_verified_trade


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
            directional_evidence={"EURUSD": {"bullish_publishers": 5, "net_bias": 0.8}},
            policy={"weights": {"technical": 40, "currency_strength": 40, "market_structure": 20,
                                "expert_consensus": 20}})
        self.assertEqual(result["ranked_count"], 1)
        row = result["opportunities"][0]
        self.assertGreater(row["score_components"]["currency_strength"], 50)
        self.assertEqual(row["score_components"]["market_structure"], 90.0)
        self.assertIsNone(row["score_components"]["expert_consensus"])
        self.assertAlmostEqual(row["score"], 76.0)
        self.assertEqual(row["consensus"]["status"], "available")
        self.assertTrue(result["coverage"]["relative_currency_strength_integrated"])

    def test_walk_forward_applies_costs_and_blocks_overlapping_trades(self):
        t = pd.date_range("2025-02-01", periods=5, freq="h", tz="UTC")
        signals = pd.DataFrame({"signal": [1, 1], "signal_time": [t[0], t[1]]})
        returns = pd.Series([0.0, 0.01, 0.01, 0.01, 0.01], index=t)
        result = evaluate_signals(signals, returns, min_trades=1,
            spread_bps=2, commission_bps=1, slippage_bps=2,
            max_holding_bars=2, allow_overlapping=False)
        self.assertEqual(result["trade_count"], 1)
        self.assertEqual(result["skipped_overlapping"], 1)
        self.assertLess(result["net_expectancy_per_trade"], result["gross_expectancy_per_trade"])
        self.assertEqual(result["costs_bps"]["total"], 5.0)

    def test_global_calendar_numeric_parser_preserves_units(self):
        self.assertEqual(_numeric("1.25M"), 1250000.0)
        self.assertEqual(_numeric("2.4%"), 2.4)
        self.assertIsNone(_numeric("n/a"))

    def test_pair_calendar_blackout_checks_both_currencies(self):
        from src.analysis.fx_ranker import rank_fx_pairs
        now = pd.Timestamp.now(tz="UTC")
        results = [{"asset": "EURUSD", "status": "available", "age_hours": 1,
                    "analysis": {"status": "ok", "direction": "bullish", "score": 70, "close": 1.1}}]
        calendar = {"status": "available", "scope": ["EUR", "USD"],
                    "covered_currencies": ["EUR", "USD"], "events": [
                        {"currency": "EUR", "importance": "high", "status": "scheduled",
                         "scheduled_at_utc": (now + pd.Timedelta(minutes=5)).isoformat()}]}
        result = rank_fx_pairs(results, economic_calendar=calendar,
            policy={"weights": {"technical": 50, "calendar_risk": 50},
                    "event_blackout_minutes_before": 30, "event_blackout_minutes_after": 30})
        self.assertEqual(result["opportunities"][0]["calendar_status"], "high_impact_pair_currency_blackout")
        self.assertEqual(result["opportunities"][0]["score_components"]["calendar_risk"], 0.0)

    def test_verified_ledger_requires_independent_audit_and_sample(self):
        trades = []
        for i in range(30):
            trades.append({
                "trade_id": f"trade-{i}", "analyst_id": "analyst one", "symbol": "EURUSD",
                "direction": "bullish", "entry": 1.1, "stop_loss": 1.0,
                "exit_price": 1.15 if i < 20 else 1.075, "fees_r": 0.0,
                "closed_at": "2026-01-10T15:00:00Z",
                "source_url": "https://example.org/closed-trade",
                "verification_status": "independently_verified",
                "verified_by": "independent-reviewer",
                "verified_at": "2026-01-11T15:00:00Z",
                "evidence_reference": f"sha256:record-{i}"})
        candidates = [{"expert_eligible": True, "named_author": "Analyst One",
                       "direction": "bullish", "assets": ["EURUSD"]}]
        result = build_verified_expert_evidence(candidates, {"trades": trades}, minimum_sample=30)
        self.assertEqual(result["EURUSD"]["verified_trade_sample_size"], 30)
        self.assertEqual(result["EURUSD"]["verified_analyst_publishers"], 1)
        self.assertEqual(result["EURUSD"]["performance_verification_status"], "independently_verified")
        trades[0]["verified_by"] = "analyst one"
        invalid, reason, _ = validate_verified_trade(trades[0])
        self.assertFalse(invalid)
        self.assertEqual(reason, "self_verification_rejected")

    def test_ohlc_backtest_uses_next_bar_and_stop_first_conservative(self):
        t = pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC")
        candles = pd.DataFrame({
            "Open": [100, 100, 100], "High": [101, 105, 102],
            "Low": [99, 97, 99], "Close": [100, 103, 101]}, index=t)
        signals = pd.DataFrame([{"symbol": "EURUSD", "signal_time": t[0],
            "direction": "bullish", "stop_loss": 98, "take_profit": 104}])
        result = backtest_ohlc_signals(signals, {"EURUSD": candles},
            initial_equity=10000, risk_fraction=0.01,
            spread_bps=1, commission_bps=1, slippage_bps=1)
        self.assertEqual(result["trade_count"], 1)
        self.assertEqual(result["trades"][0]["entry_time"], t[1].isoformat())
        self.assertEqual(result["trades"][0]["exit_reason"], "stop")
        self.assertLess(result["trades"][0]["net_pnl"], 0)
        self.assertEqual(result["initial_equity"], 10000.0)


    def test_ecb_reference_crosscheck_derives_cross_rates_without_replacing_primary(self):
        results = [{"asset": "EURUSD", "provider": "Yahoo Finance",
                    "analysis": {"close": 1.10}}]
        ecb = {"observations": [{"currency": "USD", "value": 1.10,
                                 "data_timestamp": "2026-11-24"}]}
        result = build_ecb_fx_cross_checks(results, ecb)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["coverage_pairs"], 1)
        self.assertEqual(result["checks"][0]["reference_type"],
                         "official_daily_ECB_reference_not_executable_spot")
        self.assertEqual(result["checks"][0]["difference_pct"], 0.0)

if __name__ == "__main__":
    unittest.main()
