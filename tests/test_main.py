import unittest

from src.main import daily_context_is_usable


class DailyContextFreshnessTests(unittest.TestCase):
    def test_weekend_gap_daily_bar_is_usable_with_fresh_hourly_quote(self):
        self.assertTrue(daily_context_is_usable(
            daily_status="available",
            daily_age_hours=58.3,
            max_daily_age_hours=96,
            hourly_status="available",
            hourly_quote_age_minutes=19.6,
            max_hourly_age_minutes=180,
        ))

    def test_daily_context_beyond_limit_is_rejected(self):
        self.assertFalse(daily_context_is_usable(
            "available", 96.1, 96, "available", 10, 180
        ))

    def test_stale_hourly_quote_is_rejected_even_with_fresh_daily_context(self):
        self.assertFalse(daily_context_is_usable(
            "available", 12, 96, "available", 181, 180
        ))

    def test_missing_daily_or_hourly_data_is_rejected(self):
        self.assertFalse(daily_context_is_usable(
            "unavailable", 2, 96, "available", 10, 180
        ))
        self.assertFalse(daily_context_is_usable(
            "available", 2, 96, "unavailable", None, 180
        ))

    def test_negative_or_missing_age_is_rejected(self):
        self.assertFalse(daily_context_is_usable(
            "available", None, 96, "available", 10, 180
        ))
        self.assertFalse(daily_context_is_usable(
            "available", 2, 96, "available", -1, 180
        ))


if __name__ == "__main__":
    unittest.main()
