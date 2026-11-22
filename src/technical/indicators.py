"""شاخص‌های تکنیکال قابل تنظیم؛ امتیازها احتمال موفقیت نیستند."""
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
    fast = int(cfg["ema_fast"])
    slow = int(cfg["ema_slow"])
    rsi_period = int(cfg.get("rsi_period", 14))
    atr_period = int(cfg["atr_period"])

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / rsi_period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / rsi_period, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((loss == 0) & (gain > 0), 100.0)
    rsi = rsi.mask((gain == 0) & (loss > 0), 0.0)
    rsi = rsi.mask((gain == 0) & (loss == 0), 50.0)

    previous = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - previous).abs(), (low - previous).abs()], axis=1
    ).max(axis=1)
    atr = true_range.ewm(alpha=1 / atr_period, adjust=False).mean()

    price = float(close.iloc[-1])
    ef, es = float(ema_fast.iloc[-1]), float(ema_slow.iloc[-1])
    rv, av = float(rsi.iloc[-1]), float(atr.iloc[-1])
    direction = "bullish" if price > ef > es else "bearish" if price < ef < es else "neutral"

    # Score is a transparent rule-based strength score, never a probability.
    score = 50.0
    if direction == "bullish":
        score += 20
        score += 15 if 50 <= rv <= 70 else 5 if 45 <= rv < 50 else -5 if rv > 75 else 0
    elif direction == "bearish":
        score += 20
        score += 15 if 30 <= rv <= 50 else 5 if 50 < rv <= 55 else -5 if rv < 25 else 0
    else:
        score += 5 if abs(price - ef) / max(abs(price), 1e-12) < 0.002 else 0
    score = round(max(0.0, min(100.0, score)), 1)

    stop_mult = float(cfg["stop_atr_multiple"])
    target_mult = float(cfg["target_atr_multiple"])
    if direction == "bullish":
        entry, stop, target = price, price - stop_mult * av, price + target_mult * av
    elif direction == "bearish":
        entry, stop, target = price, price + stop_mult * av, price - target_mult * av
    else:
        entry = stop = target = None

    return {
        "status": "ok", "direction": direction, "score": score,
        "close": price, "ema_fast": ef, "ema_slow": es, "rsi14": rv, "atr": av,
        "entry": entry, "stop_loss": stop, "take_profit": target,
        "risk_reward": round(target_mult / stop_mult, 2) if entry is not None and stop_mult > 0 else None,
        "method": "EMA trend + configurable RSI + ATR; daily timeframe; mechanical screening only",
        "score_type": "rule_based_strength_not_probability"
    }
