"""Dynamic, metadata-driven KOROUSH Central OHLC source adapter."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, ipaddress, os, socket, time
from typing import Any
from urllib.parse import urlsplit
import pandas as pd
import requests

_PROTOCOL = "koroush-market-data-v1"
_CAPABILITY = "market.ohlc.v1"
_CACHE_TTL = 300
_cache = {"key": None, "expires": 0.0, "sources": []}


def _stamp(value: Any) -> pd.Timestamp | None:
    try:
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None or pd.isna(stamp):
            return None
        return stamp.tz_convert("UTC")
    except (TypeError, ValueError, OverflowError):
        return None


def _safe_endpoint(value: Any) -> bool:
    try:
        parsed = urlsplit(value)
        host, port = (parsed.hostname or "").lower().rstrip("."), parsed.port
        if parsed.scheme != "https" or not host or parsed.username or parsed.password or port not in (None, 443):
            return False
        if host in {"localhost", "metadata.google.internal"} or host.endswith((".local", ".internal", ".localhost")):
            return False
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            addresses = [ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]
        return bool(addresses) and all(address.is_global for address in addresses)
    except (ValueError, OSError, TypeError):
        return False


def discover_sources(timeout: int = 8, force_refresh: bool = False) -> list[dict[str, Any]]:
    base = os.getenv("KOROUSH_CENTRAL_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("KOROUSH_CENTRAL_TENANT_KEY", "").strip()
    repo = os.getenv("GITHUB_REPOSITORY", "").strip().lower()
    if not base or not key or not repo:
        return []
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return []
    cache_key, now = f"{base}|{repo}|{hashlib.sha256(key.encode()).hexdigest()}", time.monotonic()
    if not force_refresh and _cache["key"] == cache_key and now < _cache["expires"]:
        return list(_cache["sources"])
    try:
        response = requests.get(base + "/api/extensions",
            params={"repository": repo, "kind": "data_source"},
            headers={"X-Tenant-Key": key, "Accept": "application/json"},
            timeout=max(1, min(int(timeout), 20)), allow_redirects=False)
        response.raise_for_status()
        payload = response.json()
        extensions = payload.get("extensions") if isinstance(payload, dict) else None
        if not isinstance(extensions, list):
            raise ValueError("Invalid central extension registry response")
        eligible = []
        for item in extensions:
            if not isinstance(item, dict) or item.get("kind") != "data_source" or item.get("status") != "active":
                continue
            if item.get("protocol") != _PROTOCOL or _CAPABILITY not in item.get("capabilities", []):
                continue
            pricing = item.get("pricing") or {}
            if pricing.get("cost_usd") != 0 or pricing.get("zero_cost_attested_by_admin") is not True:
                continue
            terms_url = pricing.get("terms_url", "")
            if not isinstance(terms_url, str) or not terms_url.startswith("https://"):
                continue
            if not ({"forex", "general"} & set(item.get("domains", []))):
                continue
            if item.get("repositories") and repo not in [str(v).lower() for v in item["repositories"]]:
                continue
            if _safe_endpoint(item.get("endpoint")):
                eligible.append(item)
        def priority(item):
            value = (item.get("pricing") or {}).get("priority", 0)
            return int(value) if isinstance(value, (int, float)) else 0
        eligible.sort(key=lambda item: (-priority(item), str(item.get("extension_id", "")), str(item.get("version", ""))))
        eligible = eligible[:5]
        _cache.update({"key": cache_key, "sources": eligible, "expires": now + _CACHE_TTL})
        return list(eligible)
    except Exception:
        return []


def _validate_candles(payload: dict[str, Any], symbol: str, interval: str):
    if payload.get("symbol") != symbol or payload.get("interval") != interval:
        return None
    candles = payload.get("candles")
    if not isinstance(candles, list) or not candles:
        return None
    now = pd.Timestamp(datetime.now(timezone.utc))
    rows = []
    for item in candles:
        if not isinstance(item, dict):
            continue
        opened, closed = _stamp(item.get("open_time")), _stamp(item.get("close_time"))
        if opened is None or closed is None or opened >= closed or closed > now:
            continue
        interval_seconds = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}.get(payload.get("interval"))
        if interval_seconds is not None and abs((closed - opened).total_seconds() - interval_seconds) > 2:
            continue
        try:
            values = {k: float(item[k]) for k in ("open", "high", "low", "close")}
            if any(not pd.notna(v) or v <= 0 for v in values.values()):
                continue
            if values["high"] < max(values["open"], values["close"], values["low"]):
                continue
            if values["low"] > min(values["open"], values["close"], values["high"]):
                continue
            volume = item.get("volume")
            rows.append({"Datetime": opened, "Open": values["open"], "High": values["high"],
                "Low": values["low"], "Close": values["close"],
                "Volume": float(volume) if volume is not None else None, "_close": closed})
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    if not rows:
        return None
    frame = pd.DataFrame(rows).set_index("Datetime").sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    market_time = max(row["_close"] for row in rows).isoformat()
    frame = frame.drop(columns=["_close"])
    if frame["Volume"].isna().all():
        frame = frame.drop(columns=["Volume"])
    return frame, market_time


def fetch_central_market_history(symbol: str, interval: str = "1d", limit: int = 500, timeout: int = 10):
    sources = discover_sources(timeout=min(timeout, 8))
    if not sources:
        return None
    candidates, checked = [], []
    for source in sources:
        source_id = str(source.get("extension_id", "unknown"))
        checked.append(source_id)
        try:
            response = requests.get(source["endpoint"],
                params={"symbol": symbol, "interval": interval, "limit": min(max(int(limit), 2), 1000)},
                headers={"Accept": "application/json"}, timeout=max(1, min(int(timeout), 20)))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                continue
            validated = _validate_candles(payload, symbol, interval)
            if validated is None:
                continue
            frame, market_time = validated
            candidates.append({"symbol": symbol, "status": "available",
                "provider": str(source.get("name") or source_id), "source_id": source_id,
                "source_version": source.get("version"), "source_trust": source.get("trust", "unverified"),
                "collected_at": datetime.now(timezone.utc).isoformat(), "market_timestamp": market_time,
                "market_timestamp_basis": "provider_completed_bar_close_time",
                "close": float(frame["Close"].iloc[-1]), "high": float(frame["High"].iloc[-1]),
                "low": float(frame["Low"].iloc[-1]),
                "volume": float(frame["Volume"].iloc[-1]) if "Volume" in frame else None,
                "history": frame, "sources_checked": checked.copy()})
        except Exception:
            continue
    if not candidates:
        return {"symbol": symbol, "status": "unavailable",
            "provider": "KOROUSH Central registered data sources",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "sources_checked": checked, "reason": "No registered source returned valid completed OHLC candles."}
    selected = max(candidates, key=lambda item: item["market_timestamp"])
    selected = dict(selected)
    selected.update({"sources_checked": checked, "source_selection": "freshest_valid_central_source",
        "source_candidates": len(candidates)})
    return selected
