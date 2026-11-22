import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.technical.indicators import analyze

ROOT = Path(__file__).resolve().parents[1]


class ProjectConfigurationTests(unittest.TestCase):
    def test_asset_universe_has_expected_coverage(self):
        assets = json.loads((ROOT / "config/assets.json").read_text(encoding="utf-8"))
        self.assertEqual(len(assets["forex"]), 28)
        self.assertEqual(len(assets["commodities"]), 3)
        self.assertEqual(len(assets["crypto"]), 2)
        self.assertEqual(len(assets["iran_local"]), 3)

    def test_iran_quotes_are_not_fabricated_or_enabled_without_source(self):
        assets = json.loads((ROOT / "config/assets.json").read_text(encoding="utf-8"))
        self.assertTrue(all(not item["enabled"] for item in assets["iran_local"]))


class TechnicalAnalysisTests(unittest.TestCase):
    def test_indicator_engine_returns_structured_result(self):
        close = np.linspace(100, 150, 120)
        frame = pd.DataFrame({
            "Close": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Volume": np.full(120, 1000)
        })
        settings = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))
        result = analyze(frame, settings)
        self.assertEqual(result["status"], "ok")
        self.assertIn(result["direction"], {"bullish", "bearish", "neutral"})
        self.assertGreater(result["atr"], 0)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)


if __name__ == "__main__":
    unittest.main()
