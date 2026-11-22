"""Transparent multi-factor technical screening built on pandas/numpy.

Scores are rule-based research strengths, never probabilities. Only completed
OHLC candles supplied by the data adapter are analyzed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _last_number(series: pd.Series) -> float | None:
    value = series.iloc[-1] if len(series) else np.nan
    return float(value) if pd.notna(value) and np.isfinite(value) else None


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = high.diff()
    down = -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    previous = close.shift(1)
    tr = pd.concat([(high-low), (high-previous).abs(), (low-previous).abs()], axis=1).max(axis=1)
    atr = _wilder(tr, period)
    plus_di = 100.0 * _wilder(plus_dm, period) / atr.replace(0, np.nan)
    minus_di = 100.0 * _wilder(minus_dm, period) / atr.replace(0, np.nan)
    dx = 100.0 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan)
    return _wilder(dx, period), plus_di, minus_di


def analyze(frame: pd.DataFrame, settings: dict) -> dict:
    cfg = settings["technical"]
    minimum = int(cfg.get("minimum_history_rows", 60))
    required = {"High", "Low", "Close"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return {"status": "invalid_ohlc", "rows": 0 if frame is None else len(frame)}
    data = frame.copy()
    for column in required | ({"Volume"} if "Volume" in data.columns else set()):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["High", "Low", "Close"])
    data = data[(data["High"] >= data["Low"]) & (data["Close"] > 0)]
    if len(data) < minimum:
        return {"status": "insufficient_history", "rows": len(data)}

    close, high, low = data["Close"], data["High"], data["Low"]
    fast = int(cfg.get("ema_fast", 20))
    slow = int(cfg.get("ema_slow", 50))
    rsi_period = int(cfg.get("rsi_period", 14))
    atr_period = int(cfg.get("atr_period", 14))
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    delta = close.diff()
    gain = _wilder(delta.clip(lower=0), rsi_period)
    loss = _wilder(-delta.clip(upper=0), rsi_period)
    rs = gain / loss.replace(0, np.nan)
    rsi = (100 - 100 / (1 + rs)).mask((loss == 0) & (gain > 0), 100.0)
    rsi = rsi.mask((gain == 0) & (loss > 0), 0.0).mask((gain == 0) & (loss == 0), 50.0)

    previous = close.shift(1)
    tr = pd.concat([(high-low), (high-previous).abs(), (low-previous).abs()], axis=1).max(axis=1)
    atr = _wilder(tr, atr_period)
    macd_fast = close.ewm(span=12, adjust=False).mean()
    macd_slow = close.ewm(span=26, adjust=False).mean()
    macd_line = macd_fast - macd_slow
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal
    adx, plus_di, minus_di = _adx(high, low, close, atr_period)

    price = float(close.iloc[-1])
    ef, es = float(ema_fast.iloc[-1]), float(ema_slow.iloc[-1])
    rv, av = _last_number(rsi), _last_number(atr)
    if av is None or av <= 0 or rv is None:
        return {"status": "indicator_warmup", "rows": len(data)}
    ema_slope = float((ema_slow.iloc[-1] / ema_slow.iloc[-6] - 1) * 100) if len(data) >= 6 and ema_slow.iloc[-6] else 0.0
    adx_value = _last_number(adx)
    plus_value, minus_value = _last_number(plus_di), _last_number(minus_di)
    macd_value = _last_number(macd_hist)
    macd_prev = _last_number(macd_hist.iloc[:-1]) if len(macd_hist) > 1 else None

    bullish = 0.0
    bearish = 0.0
    components = {}
    components["ema_alignment"] = 25.0 if price > ef > es else 0.0
    components["ema_slope"] = min(15.0, max(0.0, ema_slope * 12.0)) if ema_slope > 0 else 0.0
    components["rsi_momentum"] = 15.0 if 52 <= rv <= 68 else 8.0 if 50 < rv < 52 or 68 < rv <= 75 else 0.0
    components["macd_momentum"] = 15.0 if macd_value is not None and macd_value > 0 and macd_value >= (macd_prev or macd_value) else 7.0 if macd_value is not None and macd_value > 0 else 0.0
    components["trend_strength"] = (
        min(10.0, max(0.0, (adx_value - 15.0) / 2.0))
        if adx_value is not None and plus_value is not None and minus_value is not None and plus_value > minus_value
        else 0.0
    )
    lookback = min(20, max(5, len(data) // 6))
    prior_high = float(high.iloc[-lookback-1:-1].max())
    prior_low = float(low.iloc[-lookback-1:-1].min())
    components["structure"] = 15.0 if price > prior_high else 7.0 if price > float(high.iloc[-3]) else 0.0
    volume_score = None
    if "Volume" in data.columns:
        vol = data["Volume"].replace(0, np.nan)
        if vol.notna().sum() >= 20:
            baseline = vol.rolling(20, min_periods=10).mean().iloc[-1]
            if pd.notna(baseline) and baseline > 0:
                volume_score = 5.0 if vol.iloc[-1] > baseline else 0.0
    components["volume_confirmation"] = volume_score
    bullish = sum(v for v in components.values() if v is not None)

    bear_components = {
        "ema_alignment": 25.0 if price < ef < es else 0.0,
        "ema_slope": min(15.0, max(0.0, -ema_slope * 12.0)) if ema_slope < 0 else 0.0,
        "rsi_momentum": 15.0 if 32 <= rv <= 48 else 8.0 if 48 < rv < 50 or 25 <= rv < 32 else 0.0,
        "macd_momentum": 15.0 if macd_value is not None and macd_value < 0 and macd_value <= (macd_prev or macd_value) else 7.0 if macd_value is not None and macd_value < 0 else 0.0,
        "trend_strength": components["trend_strength"] if minus_value is not None and plus_value is not None and minus_value > plus_value else 0.0,
        "structure": 15.0 if price < prior_low else 7.0 if price < float(low.iloc[-3]) else 0.0,
        "volume_confirmation": volume_score,
    }
    bearish = sum(v for v in bear_components.values() if v is not None)
    direction = "bullish" if bullish >= bearish + 8 and price > ef else "bearish" if bearish >= bullish + 8 and price < ef else "neutral"
    score = round(max(bullish, bearish), 1)
    stop_mult = float(cfg.get("stop_atr_multiple", 1.5))
    target_mult = float(cfg.get("target_atr_multiple", 3.0))
    swing_low = float(low.iloc[-lookback:].min())
    swing_high = float(high.iloc[-lookback:].max())
    entry = stop = target = rr = None
    stop_basis = "not_applicable"
    target_basis = "not_applicable"
    if direction == "bullish":
        stop = min(price - stop_mult * av, swing_low)
        risk = price - stop
        structural_target = swing_high if swing_high > price else None
        target = structural_target if structural_target is not None and (structural_target-price) / risk >= 1.5 else price + target_mult * risk
        entry, rr = price, (target-price) / risk if risk > 0 else None
        stop_basis, target_basis = "max_of_ATR_buffer_and_recent_swing_low", "recent_swing_high_or_configured_R_multiple"
    elif direction == "bearish":
        stop = max(price + stop_mult * av, swing_high)
        risk = stop - price
        structural_target = swing_low if swing_low < price else None
        target = structural_target if structural_target is not None and (price-structural_target) / risk >= 1.5 else price - target_mult * risk
        entry, rr = price, (price-target) / risk if risk > 0 else None
        stop_basis, target_basis = "max_of_ATR_buffer_and_recent_swing_high", "recent_swing_low_or_configured_R_multiple"

    return {
        "status": "ok", "direction": direction, "score": score,
        "bullish_score": round(bullish, 1), "bearish_score": round(bearish, 1),
        "score_components": components if direction != "bearish" else bear_components,
        "close": price, "ema_fast": ef, "ema_slow": es, "ema_slow_slope_pct": round(ema_slope, 4),
        "rsi14": rv, "atr": av, "atr_pct": round(av / price * 100, 3),
        "adx": adx_value, "plus_di": plus_value, "minus_di": minus_value,
        "macd_histogram": macd_value, "swing_high": swing_high, "swing_low": swing_low,
        "entry": entry, "stop_loss": stop, "take_profit": target,
        "risk_reward": round(rr, 2) if rr is not None and np.isfinite(rr) else None,
        "stop_basis": stop_basis, "target_basis": target_basis,
        "method": "EMA alignment+slope, RSI, MACD histogram, ADX/DI, 20-bar structure and optional volume; daily OHLC",
        "score_type": "multi_factor_rule_based_strength_not_probability",
    }
