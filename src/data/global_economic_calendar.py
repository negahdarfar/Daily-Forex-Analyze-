"""Free no-key global FX economic calendar adapter.

Provider documents USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF and CNY coverage,
including forecast/previous/actual. Feed data is context, not a guarantee of
completeness; tentative or single-source events remain visibly qualified.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

CALENDAR_URL = "https://showmytrades.com/api/public/calendar/v1"
SUPPORTED_CURRENCIES = ("USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF")


def _utc(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _numeric(value: Any) -> float | None:
    """Parse same-unit calendar values such as 3.2%, 225K, 1.4M; never guess units."""
    if value in (None, ""):
        return None
    raw = str(value).strip().replace(",", "").replace("%", "").replace("$", "")
    multiplier = 1.0
    if raw[-1:].upper() in {"K", "M", "B"}:
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9}[raw[-1].upper()]
        raw = raw[:-1]
    try:
        return float(raw) * multiplier
    except ValueError:
        return None


def fetch_global_economic_calendar(
    timeout: int = 12,
    days: int = 7,
    max_generated_age_minutes: float = 30.0,
) -> dict[str, Any]:
    collected = datetime.now(timezone.utc)
    try:
        response = requests.get(
            CALENDAR_URL,
            params={"currency": ",".join(SUPPORTED_CURRENCIES), "impact": "high,medium", "days": min(30, max(1, int(days)))},
            headers={"User-Agent": "DailyMarketAnalyze/1.0"},
            timeout=max(1, int(timeout)),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise ValueError("Unexpected global calendar response schema")
        server_time = _utc(payload.get("server_time_iso"))
        generated = _utc(payload.get("generated_at"))
        if server_time is None or generated is None:
            raise ValueError("Calendar server_time_iso/generated_at missing or invalid")
        generated_age = (server_time - generated).total_seconds() / 60.0
        server_clock_delta = abs((collected - server_time).total_seconds()) / 60.0
        if server_clock_delta > 15:
            raise ValueError("Calendar server clock is too far from local UTC collection time")
        if generated_age < -1 or generated_age > float(max_generated_age_minutes):
            raise ValueError("Calendar body is stale or has a future generated_at")
        events = []
        for raw in payload["events"]:
            if not isinstance(raw, dict):
                continue
            currency = str(raw.get("currency", "")).upper()
            scheduled = _utc(raw.get("time"))
            if currency not in SUPPORTED_CURRENCIES or scheduled is None:
                continue
            forecast = _numeric(raw.get("forecast"))
            actual = _numeric(raw.get("actual"))
            previous = _numeric(raw.get("previous"))
            surprise = None
            surprise_pct = None
            if forecast is not None and actual is not None:
                surprise = actual - forecast
                if forecast != 0:
                    surprise_pct = surprise / abs(forecast) * 100.0
            events.append({
                "id": raw.get("id"),
                "source": "ShowMyTrades",
                "name": raw.get("title"),
                "importance": str(raw.get("impact", "")).lower(),
                "scheduled_at_utc": scheduled.isoformat(),
                "currency_scope": currency,
                "currency": currency,
                "period": raw.get("period"),
                "previous": raw.get("previous"),
                "actual": raw.get("actual"),
                "forecast": raw.get("forecast"),
                "actual_numeric": actual,
                "forecast_numeric": forecast,
                "previous_numeric": previous,
                "surprise_raw_same_unit": surprise,
                "surprise_pct_of_forecast": round(surprise_pct, 4) if surprise_pct is not None else None,
                "status": raw.get("status", "unknown"),
                "confidence": raw.get("confidence", "unknown"),
                "url": raw.get("url"),
                "directional_interpretation": "not_inferred_event_specific_economic_sign_required",
            })
        events.sort(key=lambda row: row["scheduled_at_utc"])
        event_currencies = sorted({row["currency"] for row in events})
        return {
            "source": "ShowMyTrades",
            "status": "available" if generated_age <= max_generated_age_minutes else "stale",
            "scope": list(SUPPORTED_CURRENCIES),
            "covered_currencies": list(SUPPORTED_CURRENCIES),
            "coverage": "high_and_medium_impact_major_fx_calendar_with_consensus",
            "collected_at": collected.isoformat(),
            "server_time": server_time.isoformat(),
            "updated_at": generated.isoformat(),
            "age_minutes": round(max(0.0, generated_age), 2),
            "server_clock_delta_minutes": round(server_clock_delta, 2),
            "events": events,
            "event_currencies_present": event_currencies,
            "forecast_policy": "consensus_forecast_is_provider_supplied_and_may_be_revised_until_release",
            "surprise_policy": "numeric actual-minus-forecast is reported only when values parse into matching scalar units; no generic bullish/bearish inference",
            "attribution": payload.get("attribution", {}).get("text"),
            "source_url": "https://showmytrades.com/tools/economic-calendar",
            "docs_url": "https://showmytrades.com/docs/api/economic-calendar",
            "license_note": "Free no-key feed; observe provider terms and do not resell the calendar as a standalone product.",
            "data_note": "Calendar covers eight major FX currencies plus CNY. Events may be tentative or single-source; confidence/status fields are preserved. Missing events do not prove no event risk.",
        }
    except Exception as exc:
        return {
            "source": "ShowMyTrades",
            "status": "source_error",
            "scope": list(SUPPORTED_CURRENCIES),
            "covered_currencies": [],
            "coverage": "global_fx_calendar_unavailable",
            "collected_at": collected.isoformat(),
            "updated_at": None,
            "age_minutes": None,
            "events": [],
            "reason": f"{type(exc).__name__}: {exc}",
            "data_note": "Global calendar unavailable; event risk for all covered currencies is unknown.",
        }
