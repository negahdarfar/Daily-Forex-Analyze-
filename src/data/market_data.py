"""دریافت داده‌های عمومی بازار با ثبت timestamp و محدودیت منبع."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_history(symbol: str, period: str = "6mo", interval: str = "1d") -> dict[str, Any]:
    collected_at = utc_now_iso()
    try:
        frame = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
        if frame is None or frame.empty:
            return {
                "symbol": symbol, "status": "unavailable", "reason": "منبع داده خروجی خالی برگرداند.",
                "collected_at": collected_at, "provider": "Yahoo Finance"
            }
        frame = frame.dropna(subset=["Close"])
        if frame.empty:
            return {
                "symbol": symbol, "status": "unavailable", "reason": "قیمت پایانی معتبر موجود نیست.",
                "collected_at": collected_at, "provider": "Yahoo Finance"
            }
        market_timestamp = pd.Timestamp(frame.index[-1])
        if market_timestamp.tzinfo is None:
            market_timestamp = market_timestamp.tz_localize("UTC")
        else:
            market_timestamp = market_timestamp.tz_convert("UTC")
        last = frame.iloc[-1]
        return {
            "symbol": symbol, "status": "available", "provider": "Yahoo Finance",
            "collected_at": collected_at, "market_timestamp": market_timestamp.isoformat(),
            "close": float(last["Close"]),
            "high": float(last["High"]) if pd.notna(last.get("High")) else None,
            "low": float(last["Low"]) if pd.notna(last.get("Low")) else None,
            "volume": float(last["Volume"]) if pd.notna(last.get("Volume")) else None,
            "history": frame
        }
    except Exception as exc:  # provider/network errors must not stop the full report
        return {
            "symbol": symbol, "status": "error", "reason": f"{type(exc).__name__}: {exc}",
            "collected_at": collected_at, "provider": "Yahoo Finance"
        }
