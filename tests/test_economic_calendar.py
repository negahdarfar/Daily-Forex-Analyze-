import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.data.economic_calendar import fetch_us_economic_calendar


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def payload(updated_at):
    return {
        "updatedAt": updated_at,
        "nextReleaseAt": "2026-11-25T13:30:00Z",
        "data": [{
            "source": "fed",
            "eventName": "FOMC Rate Decision",
            "importance": "high",
            "scheduledAt": "2026-11-25T19:00:00Z",
            "periodLabel": "November 2026",
            "previous": None,
            "forecast": None,
            "actual": None,
            "unit": "%",
            "canonicalUrl": "https://xoomar.com/markets/calendar/fomc"
        }],
        "meta": {"sourceAttribution": "Federal Reserve Board"},
        "canonicalUrl": "https://xoomar.com/markets/calendar"
    }


class EconomicCalendarTests(unittest.TestCase):
    @patch("src.data.economic_calendar.requests.get")
    def test_fresh_us_calendar_is_parsed_and_scope_is_explicit(self, get):
        updated = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        get.return_value = FakeResponse(payload(updated))
        result = fetch_us_economic_calendar()
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["scope"], ["USD"])
        self.assertEqual(result["events"][0]["name"], "FOMC Rate Decision")
        self.assertEqual(result["events"][0]["currency_scope"], "USD")
        self.assertIsNone(result["events"][0]["forecast"])
        self.assertIn("other seven", result["data_note"])

    @patch("src.data.economic_calendar.requests.get")
    def test_stale_calendar_is_not_marked_available(self, get):
        updated = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        get.return_value = FakeResponse(payload(updated))
        result = fetch_us_economic_calendar(max_age_hours=24)
        self.assertEqual(result["status"], "stale")
        self.assertGreater(result["age_hours"], 24)

    @patch("src.data.economic_calendar.requests.get")
    def test_provider_error_is_explicit_and_nonfatal(self, get):
        get.side_effect = TimeoutError("provider timeout")
        result = fetch_us_economic_calendar()
        self.assertEqual(result["status"], "source_error")
        self.assertEqual(result["events"], [])
        self.assertIn("unknown", result["data_note"])


if __name__ == "__main__":
    unittest.main()
