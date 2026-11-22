"""Forward-only forecast outcome tracking; never evaluates candles before publication."""
from __future__ import annotations

import pandas as pd


def evaluate_forecast(forecast: dict, candles: pd.DataFrame) -> dict:
    required = ("published_at", "direction", "target", "invalidation")
    missing = [key for key in required if forecast.get(key) in (None, "")]
    if missing:
        raise ValueError(f"Missing forecast fields: {', '.join(missing)}")
    if not {"High", "Low"}.issubset(candles.columns):
        raise ValueError("candles must contain High and Low columns")

    published = pd.Timestamp(forecast["published_at"])
    if published.tzinfo is None:
        published = published.tz_localize("UTC")
    else:
        published = published.tz_convert("UTC")

    frame = candles.copy()
    idx = pd.to_datetime(frame.index, utc=True)
    frame.index = idx
    frame = frame.loc[frame.index > published].sort_index()
    if frame.empty:
        return {"status": "pending_no_post_publication_candles", "evaluated_candles": 0}

    direction = str(forecast["direction"]).lower()
    target = float(forecast["target"])
    invalidation = float(forecast["invalidation"])
    if direction in {"bullish", "long", "buy"}:
        target_hit = frame["High"].astype(float) >= target
        invalid_hit = frame["Low"].astype(float) <= invalidation
    elif direction in {"bearish", "short", "sell"}:
        target_hit = frame["Low"].astype(float) <= target
        invalid_hit = frame["High"].astype(float) >= invalidation
    else:
        raise ValueError("direction must be bullish/long or bearish/short")

    for timestamp, target_touched, invalid_touched in zip(frame.index, target_hit, invalid_hit):
        if target_touched and invalid_touched:
            return {
                "status": "ambiguous_same_candle",
                "resolved_at": timestamp.isoformat(),
                "evaluated_candles": int(frame.index.get_loc(timestamp)) + 1,
                "warning": "Both target and invalidation were touched in one candle; intrabar order is unknown."
            }
        if target_touched:
            return {"status": "target_hit", "resolved_at": timestamp.isoformat(),
                    "evaluated_candles": int(frame.index.get_loc(timestamp)) + 1}
        if invalid_touched:
            return {"status": "invalidated", "resolved_at": timestamp.isoformat(),
                    "evaluated_candles": int(frame.index.get_loc(timestamp)) + 1}
    return {"status": "unresolved", "evaluated_candles": len(frame),
            "last_evaluated_at": frame.index[-1].isoformat()}
