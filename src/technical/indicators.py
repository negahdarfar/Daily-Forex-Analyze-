"""محاسبه شاخص‌های پایه و سناریوی مکانیکی؛ نه توصیه معاملاتی."""
from __future__ import annotations

import pandas as pd


def analyze(frame: pd.DataFrame, settings: dict) -> dict:
    cfg = settings["technical"]
    minimum = int(cfg.get("minimum_history_rows", 60))
    data = frame.dropna(subset=["Close"]).copy()
    if len(data) < minimum:
        return {"status": "insufficient_history", "rows": len(data)}
    close = data["Close"].astype(float)
    high = data["High"].astype(float)
    low = data["Low"].astype(float)
    ema_fast = close.ewm(span=int(cfg["ema_fast"]), adjust=False).mean()
    ema_slow = close.ewm(span=int(cfg["ema_slow"]), adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    prev_close = close.shift(1)
    tr = pd.concat([(high-low), (high-prev_close).abs(), (low-prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/int(cfg["atr_period"]), adjust=False).mean()
    price, ef, es, rv, av = float(close.iloc[-1]), float(ema_fast.iloc[-1]), float(ema_slow.iloc[-1]), float(rsi.iloc[-1]), float(atr.iloc[-1])
    direction = "bullish" if price > ef > es else "bearish" if price < ef < es else "neutral"
    score = 50.0
    if direction == "bullish":
        score += 25
    elif direction == "bearish":
        score += 25
    if 45 <= rv <= 65:
        score += 10
    elif rv >= 70 or rv <= 30:
        score -= 5
    score = max(0.0, min(100.0, score))
    stop_mult = float(cfg["stop_atr_multiple"])
    target_mult = float(cfg["target_atr_multiple"])
    if direction == "bullish":
        entry, stop, target = price, price - stop_mult*av, price + target_mult*av
    elif direction == "bearish":
        entry, stop, target = price, price + stop_mult*av, price - target_mult*av
    else:
        entry = stop = target = None
    return {
        "status":"ok", "direction":direction, "score":round(score,1),
        "close":price, "ema_fast":ef, "ema_slow":es, "rsi14":rv, "atr":av,
        "entry":entry, "stop_loss":stop, "take_profit":target,
        "risk_reward":round(target_mult/stop_mult,2) if entry is not None else None,
        "method":"EMA trend + RSI + ATR; daily timeframe; mechanical screening only"
    }
