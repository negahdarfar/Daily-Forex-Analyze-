"""دریافت چندمنبعی داده بازار با ثبت زمان و وضعیت منبع."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
import yfinance as yf

from src.data.central_sources import fetch_central_market_history


BINANCE_SYMBOLS = {"BTCUSDT": "BTCUSDT", "ETHUSDT": "ETHUSDT"}
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


def fetch_history(symbol: str, period: str = "6mo", interval: str = "1d", timeout: int = 10) -> dict[str, Any]:
    """Yahoo Finance adapter; data is not assumed to be real-time."""
    collected_at = utc_now_iso()
    try:
        frame = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False, timeout=max(1, int(timeout)))
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
        interval_delta = {
            "1d": pd.Timedelta(days=1),
            "1h": pd.Timedelta(hours=1),
            "4h": pd.Timedelta(hours=4),
            "15m": pd.Timedelta(minutes=15),
        }.get(interval)
        # yfinance labels OHLC bars by their opening timestamp; report the estimated
        # close time so freshness checks do not treat a fresh bar as one interval older.
        market_timestamp = _normalize_timestamp(
            pd.Timestamp(frame.index[-1]) + interval_delta
            if interval_delta is not None else frame.index[-1]
        )
        last = frame.iloc[-1]
        return {
            "symbol": symbol, "status": "available", "provider": "Yahoo Finance",
            "collected_at": collected_at, "market_timestamp": market_timestamp,
            "market_timestamp_basis": "bar_open_plus_interval_estimate",
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
        # Index candles by opening time for consistent OHLC resampling; retain close time
        # separately as the market-data freshness timestamp.
        frame.index = pd.to_datetime(pd.to_numeric(frame["open_time"]), unit="ms", utc=True)
        frame.index.name = "Datetime"
        last = frame.iloc[-1]
        last_close_time = pd.to_datetime(int(frame["close_time"].iloc[-1]), unit="ms", utc=True)
        return {
            "symbol": symbol, "status": "available", "provider": "Binance public API",
            "collected_at": collected_at, "market_timestamp": _normalize_timestamp(last_close_time),
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


def _exclude_unfinished_daily_bar(result: dict[str, Any], interval: str) -> dict[str, Any]:
    """Yahoo daily bars can include today's still-forming candle; exclude it for crypto comparison."""
    if interval != "1d" or result.get("status") != "available":
        return result
    frame = result.get("history")
    if frame is None or frame.empty:
        return result
    last_stamp = pd.Timestamp(frame.index[-1])
    if last_stamp.tzinfo is None:
        last_stamp = last_stamp.tz_localize("UTC")
    else:
        last_stamp = last_stamp.tz_convert("UTC")
    if last_stamp.date() < datetime.now(timezone.utc).date():
        return result
    completed = frame.iloc[:-1].copy()
    if completed.empty:
        return {**result, "status": "unavailable", "reason": "Yahoo Finance فقط کندل روزانه باز برگرداند."}
    last = completed.iloc[-1]
    updated = dict(result)
    updated.update({
        "history": completed,
        "market_timestamp": _normalize_timestamp(completed.index[-1] + pd.Timedelta(days=1)),
        "market_timestamp_basis": "daily_bar_open_plus_1d_estimate",
        "close": float(last["Close"]),
        "high": float(last["High"]) if pd.notna(last.get("High")) else None,
        "low": float(last["Low"]) if pd.notna(last.get("Low")) else None,
        "volume": float(last["Volume"]) if pd.notna(last.get("Volume")) else None,
        "partial_bar_excluded": True,
    })
    return updated

def fetch_asset_history(
    asset: dict[str, Any], period: str = "6mo", interval: str = "1d", timeout: int = 10
) -> dict[str, Any]:
    """Select the freshest valid OHLC history across local and central registries."""
    yahoo = fetch_history(asset["yahoo"], period=period, interval=interval, timeout=timeout)
    yahoo = _exclude_unfinished_daily_bar(yahoo, interval)
    checked = ["Yahoo Finance"]
    candidates = [yahoo] if yahoo.get("status") == "available" else []

    # Central data-source discovery is optional and cached. New admin-approved
    # sources using the stable market-data protocol are discovered without a
    # source-specific code release. The central registry credential is never
    # forwarded to the provider endpoint.
    central = fetch_central_market_history(
        asset["symbol"], interval=interval,
        limit=500 if interval == "1d" else 1000, timeout=timeout,
    )
    if central is not None:
        checked.extend(central.get("sources_checked", []))
        if central.get("status") == "available":
            candidates.append(central)

    if asset.get("category") == "crypto" and asset.get("quote_currency") == "USDT":
        binance = fetch_binance_history(asset["symbol"], interval=interval)
        checked.append("Binance public API")
        if binance.get("status") == "available":
            candidates.append(binance)
    else:
        binance = None

    if not candidates:
        providers = [yahoo] + ([central] if central is not None else []) + ([binance] if binance else [])
        reasons = "; ".join(
            f"{item.get('provider', 'source')}: {item.get('reason', item.get('status', 'unavailable'))}"
            for item in providers
        )
        return {
            "symbol": asset["symbol"], "status": "unavailable",
            "provider": "multi-source", "collected_at": utc_now_iso(),
            "sources_checked": checked, "reason": reasons or "No valid provider returned data.",
        }

    selected = dict(max(candidates, key=lambda item: item.get("market_timestamp", "")))
    selected["sources_checked"] = list(dict.fromkeys(checked))
    selected["source_selection"] = "freshest_valid_timestamp"
    selected["source_status"] = {
        item.get("provider", "source"): item.get("status", "unknown")
        for item in ([yahoo] + ([central] if central is not None else []) + ([binance] if binance else []))
    }
    selected["source_candidates"] = len(candidates)
    return selected
