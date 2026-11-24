import unittest
from datetime import date, timedelta
from unittest.mock import patch

from src.data.policy_rates import CURRENCY_AREAS, fetch_bis_policy_rates


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


def csv_payload(latest_date, prior_date, omit_area=None):
    lines = ["FREQ,REF_AREA,UNIT_MEASURE,UNIT_MULT,TIME_FORMAT,COMPILATION,DECIMALS,SOURCE_REF,SUPP_INFO_BREAKS,TITLE,TIME_PERIOD,OBS_VALUE,OBS_STATUS,OBS_CONF,OBS_PRE_BREAK"]
    for currency, area in CURRENCY_AREAS.items():
        if area == omit_area:
            continue
        title = f"Central bank policy rates - {area} - Daily - End of period"
        compilation = "Official central bank policy rate series"
        lines.append(f"D,{area},368,0,,{compilation},4,{area},,{title},{prior_date.isoformat()},1.0,A,F,")
        lines.append(f"D,{area},368,0,,{compilation},4,{area},,{title},{latest_date.isoformat()},1.5,A,F,")
    return ("\n".join(lines) + "\n").encode("utf-8")


class PolicyRateTests(unittest.TestCase):
    @patch("src.data.policy_rates.requests.get")
    def test_bis_panel_parses_all_eight_currency_areas(self, get):
        today = date.today()
        get.return_value = FakeResponse(csv_payload(today, today - timedelta(days=90)))
        result = fetch_bis_policy_rates()
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["available_currency_count"], 8)
        self.assertEqual(result["rates"]["EUR"]["policy_rate_pct"], 1.5)
        self.assertAlmostEqual(result["rates"]["EUR"]["change_90d_pp"], 0.5)
        self.assertEqual(result["rates"]["EUR"]["area_code"], "XM")
        self.assertEqual(get.call_count, 1)
        self.assertIn("WS_CBPOL", get.call_args.args[0])

    @patch("src.data.policy_rates.requests.get")
    def test_stale_policy_rate_panel_is_not_available(self, get):
        old = date.today() - timedelta(days=30)
        get.return_value = FakeResponse(csv_payload(old, old - timedelta(days=90)))
        result = fetch_bis_policy_rates(max_age_days=14)
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["available_currency_count"], 0)
        self.assertEqual(result["stale_currency_count"], 8)

    @patch("src.data.policy_rates.requests.get")
    def test_partial_currency_coverage_is_explicit(self, get):
        today = date.today()
        get.return_value = FakeResponse(csv_payload(today, today - timedelta(days=90), omit_area="NZ"))
        result = fetch_bis_policy_rates()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["available_currency_count"], 7)
        self.assertEqual(result["rates"]["NZD"]["status"], "missing")

    @patch("src.data.policy_rates.requests.get")
    def test_provider_failure_returns_source_error(self, get):
        get.side_effect = TimeoutError("BIS timeout")
        result = fetch_bis_policy_rates()
        self.assertEqual(result["status"], "source_error")
        self.assertEqual(result["rates"], {})


if __name__ == "__main__":
    unittest.main()
