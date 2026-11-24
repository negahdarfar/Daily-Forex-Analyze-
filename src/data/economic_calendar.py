"""Free US-only high-impact economic calendar adapter.

XOOMAR publishes a no-key JSON schedule sourced from US statistical agencies
and the Federal Reserve. It does not cover the other seven FX currencies and
does not publish consensus forecasts. Stale feeds are never treated as clear.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests


CALENDAR_URL = "https://xoomar.com/api/markets/calendar"


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def fetch_us_economic_calendar(timeout: int = 10, max_age_hours: float = 24.0) -> dict[str, Any]:
    """Fetch high-impact US events once per run and validate provider freshness."""
    collected_at = datetime.now(timezone.utc)
    try:
        response = requests.get(
            CALENDAR_URL,
            params={"importance": "high"},
            headers={"User-Agent": "DailyMarketAnalyze/1.0"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("Unexpected XOOMAR calendar response schema")
        updated = _parse_utc(payload.get("updatedAt"))
        if updated is None:
            raise ValueError("Calendar provider did not supply a valid updatedAt timestamp")
        age_hours = (collected_at - updated).total_seconds() / 3600.0
        if age_hours < -0.1:
            raise ValueError("Calendar updatedAt is unexpectedly in the future")
        events = []
        for raw in payload["data"]:
            if not isinstance(raw, dict):
                continue
            scheduled = _parse_utc(raw.get("scheduledAt"))
            if scheduled is None:
                continue
            events.append({
                "source": raw.get("source"),
                "name": raw.get("eventName"),
                "importance": raw.get("importance"),
                "scheduled_at_utc": scheduled.isoformat(),
                "period": raw.get("periodLabel"),
                "previous": raw.get("previous"),
                "actual": raw.get("actual"),
                "forecast": raw.get("forecast"),
                "unit": raw.get("unit"),
                "url": raw.get("canonicalUrl"),
                "currency_scope": "USD",
            })
        events.sort(key=lambda item: item["scheduled_at_utc"])
        fresh = 0 <= age_hours <= float(max_age_hours)
        return {
            "source": "XOOMAR",
            "status": "available" if fresh else "stale",
            "scope": ["USD"],
            "coverage": "US_only_high_impact_releases",
            "collected_at": collected_at.isoformat(),
            "updated_at": updated.isoformat(),
            "age_hours": round(max(0.0, age_hours), 2),
            "max_age_hours": float(max_age_hours),
            "events": events,
            "next_release_at": payload.get("nextReleaseAt"),
            "attribution": payload.get("meta", {}).get("sourceAttribution")
                or payload.get("attribution"),
            "source_url": payload.get("canonicalUrl") or "https://xoomar.com/markets/calendar",
            "docs_url": payload.get("docs") or "https://xoomar.com/markets/api",
            "license_url": payload.get("license") or "https://xoomar.com/terms",
            "forecast_policy": "forecast_is_not_published_by_this_provider",
            "data_note": (
                "High-impact US releases only. It is not a global FX calendar; "
                "the other seven currencies require separate validated providers."
            ),
        }
    except Exception as exc:
        return {
            "source": "XOOMAR",
            "status": "source_error",
            "scope": ["USD"],
            "coverage": "US_only_high_impact_releases",
            "collected_at": collected_at.isoformat(),
            "updated_at": None,
            "age_hours": None,
            "events": [],
            "reason": f"{type(exc).__name__}: {exc}",
            "data_note": "USD event risk is unknown because the calendar source failed.",
        }
