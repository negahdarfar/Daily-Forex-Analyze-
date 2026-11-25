"""Read-only MCP market-data adapters.

The first production adapter targets CohenD/fin-data-mcp's public OKX
candlestick tool. It is intentionally limited to crypto OHLC; ECB reference
rates and macro series are not misrepresented as tradable OHLC candles.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd


_BARS = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H",
    "12h": "12H", "1d": "1D", "1w": "1W", "1mo": "1M",
}
_CACHE: dict[tuple[str, str, int], tuple[float, dict[str, Any]]] = {}


def _decode_tool_result(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, (dict, list)):
        return structured
    content = getattr(result, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue
    raise ValueError("MCP tool returned no structured JSON content")


def normalize_okx_candles(
    payload: Any, symbol: str, interval: str
) -> dict[str, Any] | None:
    """Validate confirmed OKX bars and normalize to the engine's OHLCV shape."""
    if not isinstance(payload, list) or not payload:
        return None
    rows: list[dict[str, Any]] = []
    now = pd.Timestamp(datetime.now(timezone.utc))
    for item in payload:
        if not isinstance(item, (list, tuple)) or len(item) < 9:
            continue
        try:
            stamp = pd.to_datetime(int(item[0]), unit="ms", utc=True)
            values = [float(item[i]) for i in range(1, 6)]
            opened, high, low, close, volume = values
            if str(item[8]) != "1" or stamp > now:
                continue
            if any(not pd.notna(v) or v <= 0 for v in values[:4]):
                continue
            if high < max(opened, close, low) or low > min(opened, close, high):
                continue
            if not pd.notna(volume) or volume < 0:
                continue
            rows.append({
                "Datetime": stamp, "Open": opened, "High": high,
                "Low": low, "Close": close, "Volume": volume,
            })
        except (TypeError, ValueError, OverflowError):
            continue
    if not rows:
        return None
    frame = pd.DataFrame(rows).set_index("Datetime").sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    last_stamp = frame.index[-1]
    return {
        "symbol": symbol,
        "status": "available",
        "provider": "OKX via fin-data-mcp",
        "source_protocol": "MCP stdio / tools.call",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "market_timestamp": last_stamp.isoformat(),
        "market_timestamp_basis": "confirmed_exchange_candle_timestamp",
        "close": float(frame["Close"].iloc[-1]),
        "high": float(frame["High"].iloc[-1]),
        "low": float(frame["Low"].iloc[-1]),
        "volume": float(frame["Volume"].iloc[-1]),
        "history": frame,
        "sources_checked": ["CohenD/fin-data-mcp", "OKX"],
    }


async def _call_crypto_candles(inst_id: str, bar: str, limit: int) -> Any:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command="npx",
        args=["--yes", "github:CohenD/fin-data-mcp"],
        env={**os.environ, "NO_COLOR": "1"},
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "crypto_candles",
                {"instId": inst_id, "bar": bar, "limit": min(max(int(limit), 2), 300)},
            )
            if getattr(result, "isError", False):
                raise RuntimeError("fin-data-mcp crypto_candles returned an MCP error")
            return _decode_tool_result(result)


def fetch_mcp_crypto_history(
    symbol: str, interval: str = "1d", limit: int = 300, timeout: int = 25
) -> dict[str, Any] | None:
    """Fetch public OKX OHLC through MCP; disabled unless explicitly enabled."""
    if os.getenv("KOROUSH_FIN_DATA_MCP_ENABLED", "false").strip().lower() not in {"1", "true", "yes"}:
        return None
    if shutil.which("npx") is None:
        return None
    bar = _BARS.get(interval)
    if bar is None:
        return None
    inst_id = symbol.upper().replace("/", "-").replace("_", "-")
    if not inst_id.endswith("-USDT"):
        return None
    cache_key = (inst_id, bar, min(max(int(limit), 2), 300))
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and now < cached[0]:
        return cached[1]
    try:
        payload = asyncio.run(asyncio.wait_for(
            _call_crypto_candles(inst_id, bar, cache_key[2]),
            timeout=max(5, min(int(timeout), 60)),
        ))
        result = normalize_okx_candles(payload, symbol, interval)
        if result is not None:
            _CACHE[cache_key] = (now + 45, result)
        return result
    except Exception as exc:
        return {
            "symbol": symbol,
            "status": "error",
            "provider": "OKX via fin-data-mcp",
            "reason": f"{type(exc).__name__}: {exc}",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "sources_checked": ["CohenD/fin-data-mcp", "OKX"],
        }
