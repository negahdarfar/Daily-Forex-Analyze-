"""No-key official macro/reference-data adapters (not executable market quotes)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_ecb_reference_rates(timeout: int = 15) -> dict[str, Any]:
    """Fetch recent ECB euro reference rates; values are reference rates, not broker quotes."""
    url = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD+GBP+JPY+CHF+CAD+AUD+NZD.EUR.SP00.A"
    collected_at = _now()
    try:
        response = requests.get(
            url,
            params={"lastNObservations": 5, "format": "csvdata", "detail": "dataonly"},
            headers={"Accept": "text/csv", "User-Agent": "DailyMarketAnalyze/1.0"},
            timeout=timeout,
        )
        response.raise_for_status()
        from io import StringIO
        frame = pd.read_csv(StringIO(response.text))
        required = {"CURRENCY", "TIME_PERIOD", "OBS_VALUE"}
        if not required.issubset(frame.columns):
            raise ValueError(f"Unexpected ECB CSV schema: {list(frame.columns)}")
        frame["OBS_VALUE"] = pd.to_numeric(frame["OBS_VALUE"], errors="coerce")
        frame = frame.dropna(subset=["OBS_VALUE", "TIME_PERIOD"])
        rows = []
        for currency, group in frame.groupby("CURRENCY"):
            latest = group.sort_values("TIME_PERIOD").iloc[-1]
            rows.append({
                "currency": str(currency), "base": "EUR",
                "value": float(latest["OBS_VALUE"]),
                "data_timestamp": str(latest["TIME_PERIOD"]),
                "frequency": "daily", "unit": f"{currency} per EUR",
                "source": "European Central Bank", "status": "available",
                "quote_type": "official_reference_rate_not_executable_spot",
            })
        return {"source": "European Central Bank", "status": "available" if rows else "empty",
                "collected_at": collected_at, "observations": rows,
                "data_note": "Official euro reference rates; not intraday broker prices or trade execution quotes."}
    except Exception as exc:
        return {"source": "European Central Bank", "status": "source_error",
                "collected_at": collected_at, "observations": [],
                "reason": f"{type(exc).__name__}: {exc}"}


def fetch_world_bank_inflation(timeout: int = 20) -> dict[str, Any]:
    """Fetch latest annual CPI inflation observations for major FX economies."""
    countries = "USA;GBR;JPN;CHE;CAN;AUS;NZL;EMU"
    url = f"https://api.worldbank.org/v2/country/{countries}/indicator/FP.CPI.TOTL.ZG"
    collected_at = _now()
    try:
        response = requests.get(
            url, params={"format": "json", "mrnev": 3, "per_page": 100},
            headers={"User-Agent": "DailyMarketAnalyze/1.0"}, timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
            raise ValueError("Unexpected World Bank API response")
        latest: dict[str, dict[str, Any]] = {}
        for item in payload[1]:
            value = item.get("value")
            if value is None:
                continue
            code = item.get("countryiso3code") or item.get("country", {}).get("id")
            if not code:
                continue
            year = str(item.get("date", ""))
            if code not in latest or year > latest[code]["data_timestamp"]:
                latest[code] = {
                    "country_code": code, "country": item.get("country", {}).get("value", code),
                    "value": float(value), "data_timestamp": year,
                    "frequency": "annual", "unit": "percent_change_yoy",
                    "indicator": "FP.CPI.TOTL.ZG", "source": "World Bank",
                    "status": "available", "use": "slow_macro_context_not_short_term_signal",
                }
        return {"source": "World Bank", "status": "available" if latest else "empty",
                "collected_at": collected_at, "observations": list(latest.values()),
                "data_note": "Annual CPI inflation; use as slow macro context, not as a current release or intraday signal."}
    except Exception as exc:
        return {"source": "World Bank", "status": "source_error",
                "collected_at": collected_at, "observations": [],
                "reason": f"{type(exc).__name__}: {exc}"}
