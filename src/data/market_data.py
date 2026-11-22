"""دریافت چندمنبعی داده بازار با ثبت زمان و وضعیت منبع."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
import yfinance as yf


BINANCE_SYMBOLS = {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT"}
BINANCE_INTERVALS = {"1d": "1d", "1h": "1h", "4h": "4h", "15m": "15m"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_timestamp(value: Any) -> str:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.isoformat()


def fetch_history(symbol: str, period: str = "6mo", interval: str = "1d") -> dict[str, Any]:
    """Yahoo Finance adapter; data is not assumed to be real-time."""
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
        market_timestamp = _normalize_timestamp(frame.index[-1])
        last = frame.iloc[-1]
        return {
            "symbol": symbol, "status": "available", "provider": "Yahoo Finance",
            "collected_at": collected_at, "market_timestamp": market_timestamp,
            "close": float(last["Close"]),
            "high": float(last["High"]) if pd.notna(last.get("High")) else None,
            "low": float(last["Low"]) if pd.notna(last.get("Low")) else None,
            "volume": float(last["Volume"]) if pd.notna(last.get("Volume")) else None,
            "history": frame, "sources_checked": ["Yahoo Finance"]
        }
    except Exception as exc:  # provider/network errors must not stop the full report
        return {
            "symbol": symbol, "status": "error", "reason": f"{type(exc).__name__}: {exc}",
            "collected_at": collected_at, "provider": "Yahoo Finance",
            "sources_checked": ["Yahoo Finance"]
        }


def fetch_binance_history(symbol: str, interval: str = "1d", limit: int = 180) -> dict[str, Any]:
    """Public Binance spot klines; currently used only as a crypto cross-check/fallback."""
    collected_at = utc_now_iso()
    market_symbol = BINANCE_SYMBOLS.get(symbol)
    binance_interval = BINANCE_INTERVALS.get(interval)
    if not market_symbol or not binance_interval:
        return {
            "symbol": symbol, "status": "unavailable",
            "reason": "برای این دارایی یا بازه زمانی، نماد Binance تعریف نشده است.",
            "collected_at": collected_at, "provider": "Binance public API"
        }
    try:
        response = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": market_symbol, "interval": binance_interval, "limit": min(max(int(limit), 2), 1000)},
            timeout=12,
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            raise ValueError("Binance returned no klines")
        frame = pd.DataFrame(rows, columns=[
            "open_time", "Open", "High", "Low", "Close", "Volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        for column in ("Open", "High", "Low", "Close", "Volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=["Close"])
        close_time_ms = pd.to_numeric(frame["close_time"], errors="coerce")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        # Never use an unfinished candle: its displayed close is only a moving price.
        frame = frame.loc[close_time_ms <= now_ms].copy()
        if frame.empty:
            raise ValueError("Binance returned no completed candles")
        frame.index = pd.to_datetime(pd.to_numeric(frame["close_time"]), unit="ms", utc=True)
        frame.index.name = "Datetime"
        last = frame.iloc[-1]
        return {
            "symbol": symbol, "status": "available", "provider": "Binance public API",
            "collected_at": collected_at, "market_timestamp": _normalize_timestamp(frame.index[-1]),
            "close": float(last["Close"]), "high": float(last["High"]),
            "low": float(last["Low"]), "volume": float(last["Volume"]),
            "history": frame[["Open", "High", "Low", "Close", "Volume"]],
            "sources_checked": ["Binance public API"]
        }
    except Exception as exc:
        return {
            "symbol": symbol, "status": "error", "reason": f"{type(exc).__name__}: {exc}",
            "collected_at": collected_at, "provider": "Binance public API",
            "sources_checked": ["Binance public API"]
        }


def fetch_asset_history(
    asset: dict[str, Any], period: str = "6mo", interval: str = "1d"
) -> dict[str, Any]:
    """Fetch from configured sources and choose the freshest valid crypto history."""
    yahoo = fetch_history(asset["yahoo"], period=period, interval=interval)
    if asset.get("category") != "crypto":
        return yahoo

    binance = fetch_binance_history(asset["symbol"], interval=interval)
    checked = ["Yahoo Finance", "Binance public API"]
    candidates = [item for item in (yahoo, binance) if item.get("status") == "available"]
    if not candidates:
        reasons = "; ".join(
            f"{item.get('provider')}: {item.get('reason', 'unavailable')}"
            for item in (yahoo, binance)
        )
        return {
            "symbol": asset["symbol"], "status": "unavailable",
            "provider": "Yahoo Finance + Binance public API",
            "collected_at": utc_now_iso(), "sources_checked": checked, "reason": reasons
        }

    selected = max(candidates, key=lambda item: item.get("market_timestamp", ""))
    selected = dict(selected)
    selected["sources_checked"] = checked
    selected["source_selection"] = "freshest_available_timestamp"
    selected["alternate_source_status"] = {
        item["provider"]: item["status"] for item in (yahoo, binance)
    }
    return selected
