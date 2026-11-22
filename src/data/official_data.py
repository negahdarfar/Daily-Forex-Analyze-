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

def fetch_bls_macro(timeout: int = 25) -> dict[str, Any]:
    """Fetch selected US CPI, unemployment and payroll series from keyless BLS API v1."""
    url = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
    series_meta = {
        "CUSR0000SA0": {"name": "US CPI-U all items, seasonally adjusted", "unit": "index", "frequency": "monthly"},
        "LNS14000000": {"name": "US unemployment rate, seasonally adjusted", "unit": "percent", "frequency": "monthly"},
        "CES0000000001": {"name": "US total nonfarm payroll employment", "unit": "thousands of jobs", "frequency": "monthly"},
    }
    collected_at = _now()
    try:
        response = requests.post(
            url, json={"seriesid": list(series_meta)},
            headers={"Content-Type": "application/json", "User-Agent": "DailyMarketAnalyze/1.0"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "REQUEST_SUCCEEDED":
            raise ValueError(f"BLS API status: {payload.get('status')} {payload.get('message', [])}")
        rows = []
        for series in payload.get("Results", {}).get("series", []):
            sid = series.get("seriesID")
            meta = series_meta.get(sid)
            if not meta:
                continue
            observations = []
            for point in series.get("data", []):
                period = str(point.get("period", ""))
                if not period.startswith("M") or period == "M13":
                    continue
                try:
                    value = float(point["value"].replace(",", ""))
                except (TypeError, ValueError, KeyError):
                    continue
                observations.append({
                    "year": str(point.get("year", "")), "period": period,
                    "period_name": point.get("periodName"), "value": value,
                    "footnotes": [f.get("text") for f in point.get("footnotes", []) if f.get("text")],
                })
            observations.sort(key=lambda x: (x["year"], x["period"]), reverse=True)
            if observations:
                latest = observations[0]
                previous = observations[1] if len(observations) > 1 else None
                rows.append({
                    "series_id": sid, **meta, "latest": latest, "previous": previous,
                    "change_from_previous": round(latest["value"] - previous["value"], 6) if previous else None,
                    "data_timestamp": f"{latest['year']}-{latest['period']}",
                    "source": "US Bureau of Labor Statistics", "status": "available",
                })
        return {
            "source": "US Bureau of Labor Statistics", "status": "available" if rows else "empty",
            "collected_at": collected_at, "observations": rows,
            "data_note": "BLS Public Data API v1 (no registration key); monthly US labour-price indicators. Latest observations may be revised or preliminary; this is not a live market quote.",
            "endpoint": url, "series_requested": list(series_meta),
        }
    except Exception as exc:
        return {"source": "US Bureau of Labor Statistics", "status": "source_error",
                "collected_at": collected_at, "observations": [],
                "reason": f"{type(exc).__name__}: {exc}"}


def fetch_cftc_cot(timeout: int = 25) -> dict[str, Any]:
    """Fetch latest Legacy Futures Only COT positioning for major FX, gold, silver and crude contracts."""
    url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
    contracts = {
        "099741": "Euro FX", "096742": "British Pound", "097741": "Japanese Yen",
        "092741": "Swiss Franc", "090741": "Canadian Dollar", "232741": "Australian Dollar",
        "112741": "New Zealand Dollar", "088691": "Gold", "084691": "Silver",
        "067651": "WTI Crude Oil",
    }
    collected_at = _now()
    try:
        code_filter = ",".join(f"'{code}'" for code in contracts)
        response = requests.get(
            url,
            params={
                "$select": "cftc_contract_market_code,market_and_exchange_names,report_date_as_yyyy_mm_dd,open_interest_all,noncomm_positions_long_all,noncomm_positions_short_all,comm_positions_long_all,comm_positions_short_all",
                "$where": f"cftc_contract_market_code in ({code_filter})",
                "$order": "report_date_as_yyyy_mm_dd DESC",
                "$limit": 100,
            },
            headers={"User-Agent": "DailyMarketAnalyze/1.0", "Accept": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        latest_by_code = {}
        for item in payload if isinstance(payload, list) else []:
            code = str(item.get("cftc_contract_market_code", ""))
            if code not in contracts or code in latest_by_code:
                continue
            try:
                oi = float(item["open_interest_all"])
                noncomm_long = float(item["noncomm_positions_long_all"])
                noncomm_short = float(item["noncomm_positions_short_all"])
                comm_long = float(item["comm_positions_long_all"])
                comm_short = float(item["comm_positions_short_all"])
                if oi <= 0:
                    continue
            except (TypeError, ValueError, KeyError):
                continue
            net = noncomm_long - noncomm_short
            latest_by_code[code] = {
                "contract_code": code, "contract": contracts[code],
                "market_name": item.get("market_and_exchange_names"),
                "report_date": item.get("report_date_as_yyyy_mm_dd"),
                "open_interest": oi, "noncommercial_long": noncomm_long,
                "noncommercial_short": noncomm_short, "noncommercial_net": net,
                "noncommercial_net_pct_open_interest": round(100.0 * net / oi, 3),
                "commercial_net": comm_long - comm_short,
                "frequency": "weekly", "source": "CFTC", "status": "available",
                "interpretation": "positioning_context_not_a_directional_trade_signal",
            }
        observations = sorted(latest_by_code.values(), key=lambda x: x["contract"])
        return {
            "source": "CFTC", "status": "available" if observations else "empty",
            "collected_at": collected_at, "observations": observations,
            "data_note": "Legacy Futures Only Commitments of Traders; weekly positions as of Tuesday, normally published Friday. Net positions are contextual positioning data, not proof of future price direction.",
            "endpoint": url, "contracts_requested": len(contracts),
        }
    except Exception as exc:
        return {"source": "CFTC", "status": "source_error",
                "collected_at": collected_at, "observations": [],
                "reason": f"{type(exc).__name__}: {exc}"}

