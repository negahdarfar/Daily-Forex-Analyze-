import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.data.market_data import fetch_history


class MarketDataTimeoutTests(unittest.TestCase):
    @patch("src.data.market_data.yf.Ticker")
    def test_yahoo_history_receives_explicit_timeout(self, ticker_factory):
        index = pd.DatetimeIndex(["2026-11-23T00:00:00Z"])
        frame = pd.DataFrame(
            {"Close": [1.1], "High": [1.2], "Low": [1.0], "Volume": [100]},
            index=index,
        )
        ticker = MagicMock()
        ticker.history.return_value = frame
        ticker_factory.return_value = ticker
        result = fetch_history("EURUSD=X", timeout=7)
        self.assertEqual(result["status"], "available")
        ticker.history.assert_called_once_with(
            period="6mo", interval="1d", auto_adjust=False, timeout=7
        )

    @patch("src.data.market_data.yf.Ticker")
    def test_timeout_failure_is_captured_as_source_error(self, ticker_factory):
        ticker = MagicMock()
        ticker.history.side_effect = TimeoutError("request timed out")
        ticker_factory.return_value = ticker
        result = fetch_history("EURUSD=X", timeout=2)
        self.assertEqual(result["status"], "error")
        self.assertIn("TimeoutError", result["reason"])


if __name__ == "__main__":
    unittest.main()
