import json
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
import pandas as pd

from src.technical.indicators import analyze
from src.experts.registry import assess_profile
from src.experts.performance import calculate_performance, realized_r_multiple, assess_trader_history
from src.data.news import classify_relevance, collect_news
from src.data.market_data import fetch_asset_history
from src.data.source_registry import load_source_registry, summarize_source_registry, merge_active_rss_sources
from src.data.official_data import fetch_ecb_reference_rates, fetch_world_bank_inflation, fetch_bls_macro, fetch_cftc_cot, fetch_fred_public_series
from src.experts.forecast_tracking import evaluate_forecast
from src.experts.analysis_ingestion import extract_analysis_candidates

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

    def test_analysis_registry_contains_100_unique_sources(self):
        registry = load_source_registry(ROOT / "config/analysis_sources.json")
        summary = summarize_source_registry(registry)
        self.assertEqual(summary["total"], 100)
        self.assertEqual(summary["enabled"], 9)
        self.assertEqual(len({item["id"] for item in registry["sources"]}), 100)

    def test_analysis_ingestion_extracts_only_explicit_fields(self):
        items = [{
            "title": "EUR/USD bullish Elliott wave analysis on 4H",
            "summary": "Upside outlook; target 1.0950, stop-loss 1.0720.",
            "source": "Example Research", "author": "Analyst A",
            "url": "https://example.com/eurusd", "published_at": "2026-11-22T08:00:00+00:00",
            "collected_at": "2026-11-22T08:05:00+00:00", "status": "dated"
        }]
        result = extract_analysis_candidates(items, ["EURUSD"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["assets"], ["EURUSD"])
        self.assertEqual(result[0]["direction"], "bullish")
        self.assertEqual(result[0]["timeframes"], ["4h"])
        self.assertEqual(result[0]["levels"]["target"], 1.095)
        self.assertEqual(result[0]["verification_status"], "unverified_source_claim")

    def test_analysis_ingestion_deduplicates_and_does_not_invent_direction(self):
        item = {
            "title": "Gold technical analysis: support and resistance",
            "summary": "Key levels discussed without a directional call.",
            "source": "Example", "url": "https://example.com/gold", "status": "dated"
        }
        result = extract_analysis_candidates([item, item], ["XAUUSD"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["direction"], "not_stated")
        self.assertEqual(result[0]["timeframes"], [])
        self.assertEqual(result[0]["levels"], {})

    def test_disabled_rss_source_is_not_requested(self):
        with patch("src.data.news.requests.get") as get:
            items = collect_news([{"name": "Disabled", "url": "https://example.com/feed.xml", "enabled": False}])
        get.assert_not_called()
        self.assertEqual(items, [])

    def test_unconnected_sources_are_not_enabled_and_authority_order_is_preserved(self):
        registry = load_source_registry(ROOT / "config/analysis_sources.json")
        unconnected = [item for item in registry["sources"] if item["status"] == "registered_not_connected"]
        self.assertEqual(len(unconnected), 91)
        self.assertTrue(all(not item["enabled"] for item in unconnected))
        self.assertEqual(registry["sources"][0]["name"], "Federal Reserve")
        self.assertEqual(registry["sources"][34]["name"], "US SEC EDGAR")
        self.assertEqual(registry["sources"][35]["name"], "Investing.com")
        self.assertEqual(registry["sources"][49]["name"], "Investopedia")
        self.assertEqual(registry["sources"][50]["name"], "Reuters")
        self.assertEqual(registry["sources"][99]["name"], "FOREX.com")

    def test_rss_sources_are_public_and_named(self):
        config = json.loads((ROOT / "config/news_sources.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(config["sources"]), 1)
        self.assertTrue(all(item["url"].startswith("https://") for item in config["sources"]))

    def test_registry_controls_rss_activation(self):
        registry = load_source_registry(ROOT / "config/analysis_sources.json")
        config = json.loads((ROOT / "config/news_sources.json").read_text(encoding="utf-8"))
        active = merge_active_rss_sources(config["sources"], registry)
        self.assertEqual(len(active), 5)
        self.assertEqual({item["name"] for item in active}, {"FXStreet", "CNBC", "BBC Business", "Federal Reserve", "US Bureau of Labor Statistics"})
        self.assertTrue(all(item["url"].startswith("https://") for item in active))
        self.assertFalse(any(item["name"] == "Yahoo Finance" for item in active))


class MarketDataSourceTests(unittest.TestCase):
    def test_crypto_selects_freshest_valid_source(self):
        yahoo = {
            "status": "available", "provider": "Yahoo Finance",
            "market_timestamp": "2026-11-20T00:00:00+00:00", "close": 90000
        }
        binance = {
            "status": "available", "provider": "Binance public API",
            "market_timestamp": "2026-11-22T00:00:00+00:00", "close": 91000
        }
        with patch("src.data.market_data.fetch_history", return_value=yahoo), patch("src.data.market_data.fetch_binance_history", return_value=binance):
            result = fetch_asset_history({"symbol": "BTCUSD", "yahoo": "BTC-USD", "category": "crypto"})
        self.assertEqual(result["provider"], "Binance public API")
        self.assertEqual(result["close"], 91000)
        self.assertEqual(result["source_selection"], "freshest_available_timestamp")
        self.assertEqual(len(result["sources_checked"]), 2)

    def test_non_crypto_does_not_call_binance(self):
        yahoo = {"status": "available", "provider": "Yahoo Finance"}
        with patch("src.data.market_data.fetch_history", return_value=yahoo), patch("src.data.market_data.fetch_binance_history") as binance:
            result = fetch_asset_history({"symbol": "EURUSD", "yahoo": "EURUSD=X", "category": "forex"})
        binance.assert_not_called()
        self.assertEqual(result["provider"], "Yahoo Finance")

class OfficialMacroDataTests(unittest.TestCase):
    @patch("src.data.official_data.requests.get")
    def test_ecb_adapter_parses_official_reference_rates(self, get):
        class Response:
            text = "CURRENCY,TIME_PERIOD,OBS_VALUE\nUSD,2026-11-20,1.15\nGBP,2026-11-20,0.88\n"
            def raise_for_status(self): pass
        get.return_value = Response()
        result = fetch_ecb_reference_rates()
        self.assertEqual(result["status"], "available")
        self.assertEqual(len(result["observations"]), 2)
        self.assertEqual(result["observations"][0]["quote_type"], "official_reference_rate_not_executable_spot")

    @patch("src.data.official_data.requests.get")
    def test_world_bank_adapter_keeps_annual_frequency(self, get):
        class Response:
            def raise_for_status(self): pass
            def json(self):
                return [{"pages": 1}, [
                    {"countryiso3code": "USA", "country": {"value": "United States"}, "date": "2024", "value": 3.2},
                    {"countryiso3code": "GBR", "country": {"value": "United Kingdom"}, "date": "2024", "value": 2.5},
                ]]
        get.return_value = Response()
        result = fetch_world_bank_inflation()
        self.assertEqual(result["status"], "available")
        self.assertTrue(all(x["frequency"] == "annual" for x in result["observations"]))

    @patch("src.data.official_data.requests.post")
    def test_bls_adapter_parses_monthly_series_without_api_key(self, post):
        class Response:
            def raise_for_status(self): pass
            def json(self):
                return {"status": "REQUEST_SUCCEEDED", "Results": {"series": [
                    {"seriesID": "CUSR0000SA0", "data": [
                        {"year": "2026", "period": "M10", "periodName": "October", "value": "325.1", "footnotes": []},
                        {"year": "2026", "period": "M09", "periodName": "September", "value": "324.8", "footnotes": []},
                    ]}
                ]}}
        post.return_value = Response()
        result = fetch_bls_macro()
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["observations"][0]["latest"]["value"], 325.1)
        self.assertAlmostEqual(result["observations"][0]["change_from_previous"], 0.3)
        self.assertEqual(result["observations"][0]["frequency"], "monthly")
        self.assertNotIn("registrationkey", post.call_args.kwargs["json"])

    @patch("src.data.official_data.requests.get")
    def test_fred_public_csv_adapter_reads_keyless_series(self, get):
        class Response:
            text = "observation_date,DFF\n2026-11-20,3.75\n2026-11-19,3.75\n"
            def raise_for_status(self): pass
        get.return_value = Response()
        result = fetch_fred_public_series()
        self.assertEqual(result["status"], "available")
        self.assertEqual(len(result["observations"]), 6)
        self.assertEqual(result["observations"][0]["latest"]["value"], 3.75)
        self.assertEqual(result["observations"][0]["frequency"], "daily")
        self.assertEqual(get.call_count, 6)

    @patch("src.data.official_data.requests.get")
    def test_cftc_adapter_calculates_noncommercial_net_position(self, get):
        class Response:
            def raise_for_status(self): pass
            def json(self):
                return [
                    {
                        "cftc_contract_market_code": "099741", "market_and_exchange_names": "EURO FX",
                        "report_date_as_yyyy_mm_dd": "2026-11-17", "open_interest_all": "100000",
                        "noncomm_positions_long_all": "45000", "noncomm_positions_short_all": "30000",
                        "comm_positions_long_all": "25000", "comm_positions_short_all": "40000",
                    },
                    {
                        "cftc_contract_market_code": "099741", "market_and_exchange_names": "EURO FX",
                        "report_date_as_yyyy_mm_dd": "2026-11-10", "open_interest_all": "100000",
                        "noncomm_positions_long_all": "40000", "noncomm_positions_short_all": "30000",
                        "comm_positions_long_all": "25000", "comm_positions_short_all": "35000",
                    },
                ]
        get.return_value = Response()
        result = fetch_cftc_cot()
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["observations"][0]["noncommercial_net"], 15000)
        self.assertEqual(result["observations"][0]["noncommercial_net_pct_open_interest"], 15.0)
        self.assertEqual(result["observations"][0]["frequency"], "weekly")
        self.assertEqual(result["observations"][0]["history_weeks"], 2)
        self.assertIsNone(result["observations"][0]["net_position_52w_percentile"])
        self.assertIsNone(result["observations"][0]["net_position_52w_zscore"])


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
        self.assertEqual(result["score_type"], "multi_factor_rule_based_strength_not_probability")

    def test_monotonic_series_has_finite_rsi(self):
        result = analyze(self.frame, self.settings)
        self.assertTrue(np.isfinite(result["rsi14"]))
        self.assertEqual(result["rsi14"], 100.0)

    def test_multifactor_engine_exposes_structure_and_dynamic_risk_metrics(self):
        result = analyze(self.frame, self.settings)
        self.assertIn("macd_histogram", result)
        self.assertIn("adx", result)
        self.assertIn("swing_high", result)
        self.assertIn("swing_low", result)
        self.assertIn("atr_pct", result)
        self.assertIn("stop_basis", result)
        self.assertIn("target_basis", result)
        self.assertEqual(result["score_type"], "multi_factor_rule_based_strength_not_probability")
        if result["take_profit"] is not None:
            self.assertGreaterEqual(result["risk_reward"], 1.5)
        else:
            self.assertIsNone(result["risk_reward"])
            self.assertEqual(result["execution_status"], "no_valid_structural_target")
        self.assertNotIn("configured_R_multiple", result["target_basis"])


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


    def test_news_classifier_identifies_macro_and_asset_news(self):
        self.assertEqual(classify_relevance("Federal Reserve signals rate cut"), "market_relevant")
        self.assertEqual(classify_relevance("Gold prices rise as dollar weakens"), "market_relevant")

    def test_news_classifier_filters_unrelated_business_headlines(self):
        self.assertEqual(classify_relevance("Retailer opens new stores", "Hiring plans expand"), "general_business")


    def test_forecast_evaluation_ignores_prepublication_candles(self):
        candles = pd.DataFrame(
            {"High": [120, 111], "Low": [90, 105]},
            index=pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"])
        )
        result = evaluate_forecast({
            "published_at": "2026-01-01T12:00:00Z",
            "direction": "bullish", "target": 110, "invalidation": 95
        }, candles)
        self.assertEqual(result["status"], "target_hit")
        self.assertEqual(result["evaluated_candles"], 1)

    def test_forecast_evaluation_marks_same_candle_touch_ambiguous(self):
        candles = pd.DataFrame(
            {"High": [112], "Low": [94]},
            index=pd.to_datetime(["2026-01-02T00:00:00Z"])
        )
        result = evaluate_forecast({
            "published_at": "2026-01-01T12:00:00Z",
            "direction": "bullish", "target": 110, "invalidation": 95
        }, candles)
        self.assertEqual(result["status"], "ambiguous_same_candle")

    def test_forecast_profile_without_evidence_is_unverified(self):
        result = assess_profile({"name": "Example"})
        self.assertEqual(result["status"], "unverified")
        self.assertGreater(len(result["missing_evidence"]), 0)


if __name__ == "__main__":
    unittest.main()
