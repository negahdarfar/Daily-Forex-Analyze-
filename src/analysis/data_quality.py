"""Reusable market-data quality gates."""
from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd


def validate_ohlc(frame: pd.DataFrame | None) -> dict:
    required = {"Open", "High", "Low", "Close"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return {"status": "invalid", "rows_in": 0 if frame is None else len(frame), "rows_valid": 0, "issues": ["missing_or_empty_ohlc"]}
    data = frame.copy()
    for col in required:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    issues = []
    if not isinstance(data.index, pd.DatetimeIndex):
        return {"status": "invalid", "rows_in": len(data), "rows_valid": 0, "issues": ["datetime_index_required"]}
    if data.index.has_duplicates:
        issues.append("duplicate_timestamps")
    if not data.index.is_monotonic_increasing:
        issues.append("timestamps_not_monotonic")
    valid = data.dropna(subset=list(required))
    valid = valid[(valid[list(required)] > 0).all(axis=1)]
    valid = valid[(valid["High"] >= valid[["Open", "Close", "Low"]].max(axis=1)) &
                  (valid["Low"] <= valid[["Open", "Close", "High"]].min(axis=1))]
    if len(valid) != len(data):
        issues.append("invalid_or_missing_ohlc_rows")
    return {"status": "available" if len(valid) == len(data) and not issues else "degraded",
            "rows_in": len(data), "rows_valid": len(valid), "issues": issues}


def age_status(timestamp: str | None, max_age_minutes: float, now: datetime | None = None) -> dict:
    if not timestamp:
        return {"status": "unknown", "age_minutes": None}
    try:
        stamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        age = (current.astimezone(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds() / 60
        if age < 0:
            return {"status": "invalid_future_timestamp", "age_minutes": round(age, 2)}
        return {"status": "fresh" if age <= max_age_minutes else "stale", "age_minutes": round(age, 2)}
    except (TypeError, ValueError):
        return {"status": "invalid_timestamp", "age_minutes": None}
