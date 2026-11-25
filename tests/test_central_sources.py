import os
import unittest
from unittest.mock import Mock, patch
from src.data import central_sources, market_data


class CentralSourceTests(unittest.TestCase):
    def setUp(self):
        central_sources._cache.update({"key": None, "expires": 0, "sources": []})
        self.env = patch.dict(os.environ, {
            "KOROUSH_CENTRAL_BASE_URL": "https://central.example.org",
            "KOROUSH_CENTRAL_TENANT_KEY": "kor_test_key",
            "GITHUB_REPOSITORY": "negahdarfar/daily-forex-analyze-",
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        central_sources._cache.update({"key": None, "expires": 0, "sources": []})

    def test_registry_filters_inactive_and_wrong_protocol(self):
        good = {"kind": "data_source", "status": "active", "protocol": "koroush-market-data-v1",
            "capabilities": ["market.ohlc.v1"], "domains": ["forex"],
            "endpoint": "https://prices.example.org/ohlc", "extension_id": "feed.good",
            "version": "1.0.0", "name": "Good", "pricing": {"cost_usd": 0, "zero_cost_attested_by_admin": True, "terms_url": "https://prices.example.org/terms"}}
        off = dict(good, status="disabled", extension_id="feed.off")
        bad = dict(good, protocol="other", extension_id="feed.bad")
        unknown_cost = dict(good, extension_id="feed.unknown", pricing={"status": "unverified"})
        response = Mock()
        response.json.return_value = {"extensions": [good, off, bad, unknown_cost]}
        response.raise_for_status.return_value = None
        with patch.object(central_sources, "_safe_endpoint", return_value=True), patch.object(central_sources.requests, "get", return_value=response):
            result = central_sources.discover_sources(force_refresh=True)
        self.assertEqual([x["extension_id"] for x in result], ["feed.good"])

    def test_ohlc_contract_rejects_future_and_invalid_bars(self):
        payload = {"symbol": "EURUSD", "interval": "1h", "candles": [
            {"open_time": "2026-11-25T01:00:00Z", "close_time": "2026-11-25T02:00:00Z",
             "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15},
            {"open_time": "2999-01-01T00:00:00Z", "close_time": "2999-01-01T01:00:00Z",
             "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15},
            {"open_time": "2026-11-25T02:00:00Z", "close_time": "2026-11-25T03:00:00Z",
             "open": 1.1, "high": 1.0, "low": 0.9, "close": 1.15}]}
        result = central_sources._validate_candles(payload, "EURUSD", "1h")
        self.assertIsNotNone(result)
        self.assertEqual(len(result[0]), 1)

    def test_wrong_symbol_is_rejected(self):
        self.assertIsNone(central_sources._validate_candles(
            {"symbol": "GBPUSD", "interval": "1h", "candles": []}, "EURUSD", "1h"))

    def test_registry_is_disabled_without_credentials(self):
        with patch.dict(os.environ, {"KOROUSH_CENTRAL_TENANT_KEY": "", "GITHUB_REPOSITORY": ""}):
            self.assertEqual(central_sources.discover_sources(force_refresh=True), [])

    def test_market_data_selects_freshest_valid_central_candidate(self):
        yahoo = {"symbol": "EURUSD", "status": "available", "provider": "Yahoo Finance",
                 "market_timestamp": "2026-11-25T02:00:00+00:00", "history": object()}
        central = {"symbol": "EURUSD", "status": "available", "provider": "Central FX",
                   "market_timestamp": "2026-11-25T03:00:00+00:00", "history": object(),
                   "sources_checked": ["provider.fx-public-feed"]}
        with patch.object(market_data, "fetch_history", return_value=yahoo), \
             patch.object(market_data, "_exclude_unfinished_daily_bar", return_value=yahoo), \
             patch.object(market_data, "fetch_central_market_history", return_value=central):
            result = market_data.fetch_asset_history(
                {"symbol": "EURUSD", "yahoo": "EURUSD", "category": "forex"}, interval="1h")
        self.assertEqual(result["provider"], "Central FX")

    def test_local_provider_remains_fallback_when_central_is_unavailable(self):
        yahoo = {"symbol": "EURUSD", "status": "available", "provider": "Yahoo Finance",
                 "market_timestamp": "2026-11-25T02:00:00+00:00", "history": object()}
        central = {"symbol": "EURUSD", "status": "unavailable",
                   "sources_checked": ["provider.fx-public-feed"]}
        with patch.object(market_data, "fetch_history", return_value=yahoo), \
             patch.object(market_data, "_exclude_unfinished_daily_bar", return_value=yahoo), \
             patch.object(market_data, "fetch_central_market_history", return_value=central):
            result = market_data.fetch_asset_history(
                {"symbol": "EURUSD", "yahoo": "EURUSD", "category": "forex"}, interval="1h")
        self.assertEqual(result["provider"], "Yahoo Finance")


if __name__ == "__main__":
    unittest.main()
