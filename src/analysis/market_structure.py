"""Non-repainting OHLC structure annotations using confirmed pivots."""
from __future__ import annotations
import pandas as pd


def analyze_market_structure(frame: pd.DataFrame, left: int = 3, right: int = 3, fvg_min_atr: float = 0.0) -> dict:
    required = {"Open", "High", "Low", "Close"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return {"status": "invalid_ohlc", "events": []}
    if left < 1 or right < 1:
        raise ValueError("pivot windows must be positive")
    data = frame.copy()
    for col in required:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=list(required)).sort_index()
    data = data[~data.index.duplicated(keep="last")]
    valid = (data["High"] >= data[["Open", "Close", "Low"]].max(axis=1)) & (data["Low"] <= data[["Open", "Close", "High"]].min(axis=1))
    data = data.loc[valid]
    if len(data) < left + right + 3:
        return {"status": "insufficient_history", "events": []}
    events = []
    pivots_high, pivots_low = [], []
    # A pivot is emitted only at its confirmation bar, never at its historical pivot bar.
    for i in range(left, len(data) - right):
        h = float(data["High"].iloc[i])
        l = float(data["Low"].iloc[i])
        if h >= float(data["High"].iloc[i-left:i+right+1].max()) and (data["High"].iloc[i-left:i+right+1] == h).sum() == 1:
            pivots_high.append((i, h))
            events.append({"type": "swing_high_confirmed", "pivot_index": str(data.index[i]), "confirmed_at": str(data.index[i+right]), "price": h})
        if l <= float(data["Low"].iloc[i-left:i+right+1].min()) and (data["Low"].iloc[i-left:i+right+1] == l).sum() == 1:
            pivots_low.append((i, l))
            events.append({"type": "swing_low_confirmed", "pivot_index": str(data.index[i]), "confirmed_at": str(data.index[i+right]), "price": l})
    last_high = last_low = None
    previous_direction = None
    tr = (data["High"] - data["Low"]).rolling(14, min_periods=1).mean()
    for i in range(len(data)):
        confirmed_pivots_high = [p for p in pivots_high if p[0] + right == i]
        confirmed_pivots_low = [p for p in pivots_low if p[0] + right == i]
        if confirmed_pivots_high:
            last_high = confirmed_pivots_high[-1][1]
        if confirmed_pivots_low:
            last_low = confirmed_pivots_low[-1][1]
        close = float(data["Close"].iloc[i])
        if last_high is not None and close > last_high:
            kind = "BOS" if previous_direction in (None, "bullish") else "CHoCH"
            events.append({"type": kind, "direction": "bullish", "at": str(data.index[i]), "level": last_high})
            previous_direction = "bullish"
            last_high = None
        elif last_low is not None and close < last_low:
            kind = "BOS" if previous_direction in (None, "bearish") else "CHoCH"
            events.append({"type": kind, "direction": "bearish", "at": str(data.index[i]), "level": last_low})
            previous_direction = "bearish"
            last_low = None
    gaps = []
    for i in range(2, len(data)):
        atr = float(tr.iloc[i])
        if atr <= 0:
            continue
        low_now, high_now = float(data["Low"].iloc[i]), float(data["High"].iloc[i])
        high_two, low_two = float(data["High"].iloc[i-2]), float(data["Low"].iloc[i-2])
        if low_now > high_two and low_now - high_two >= fvg_min_atr * atr:
            gaps.append({"type": "bullish_FVG", "at": str(data.index[i]), "low": high_two, "high": low_now})
        if high_now < low_two and low_two - high_now >= fvg_min_atr * atr:
            gaps.append({"type": "bearish_FVG", "at": str(data.index[i]), "low": high_now, "high": low_two})
    events.extend(gaps)
    events.sort(key=lambda e: e.get("confirmed_at", e.get("at", "")))
    return {"status": "available", "events": events, "pivot_left": left, "pivot_right": right,
            "non_repainting_note": "Swing points are timestamped at confirmation, not at the pivot candle."}
