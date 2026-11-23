"""Deterministic multi-timeframe opportunity screening.

This module never treats missing costs, fundamentals, news, or liquidity as zero.
It separates technical candidates from execution-qualified opportunities.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from src.technical.indicators import analyze


SCHEMA_VERSION = "1.0.0"
TIMEFRAMES = ("1d", "4h", "1h")


def _clean_ohlc(frame: pd.DataFrame | None) -> pd.DataFrame:
    required = {"Open", "High", "Low", "Close"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame()
    data = frame.copy()
    if not isinstance(data.index, pd.DatetimeIndex):
        return pd.DataFrame()
    if data.index.tz is None:
        data.index = data.index.tz_localize("UTC")
    else:
        data.index = data.index.tz_convert("UTC")
    for col in required | ({"Volume"} if "Volume" in data.columns else set()):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data[~data.index.duplicated(keep="last")].sort_index()
    data = data.dropna(subset=["Open", "High", "Low", "Close"])
    valid = (
        (data[["Open", "High", "Low", "Close"]] > 0).all(axis=1)
        & (data["High"] >= data[["Open", "Close", "Low"]].max(axis=1))
        & (data["Low"] <= data[["Open", "Close", "High"]].min(axis=1))
    )
    return data.loc[valid]


def completed_hourly_candles(hourly: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    """Keep only fully closed hourly bars; source indexes are candle opening times."""
    data = _clean_ohlc(hourly)
    if data.empty:
        return data
    now_ts = pd.Timestamp(now or datetime.now(timezone.utc))
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    else:
        now_ts = now_ts.tz_convert("UTC")
    return data.loc[(data.index + pd.Timedelta(hours=1)) <= now_ts]


def resample_completed_4h(hourly: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    """Build UTC 4h candles only from four correctly aligned, consecutive closed 1h bars."""
    data = completed_hourly_candles(hourly, now=now)
    if data.empty:
        return data
    # Reject off-grid timestamps rather than silently assigning them to an OHLC bucket.
    if ((data.index.minute != 0) | (data.index.second != 0) | (data.index.microsecond != 0)).any():
        data = data.loc[
            (data.index.minute == 0)
            & (data.index.second == 0)
            & (data.index.microsecond == 0)
        ]
    if data.empty:
        return data
    now_ts = pd.Timestamp(now or datetime.now(timezone.utc))
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    else:
        now_ts = now_ts.tz_convert("UTC")

    rows = []
    labels = []
    for bucket_start, group in data.groupby(
        pd.Grouper(freq="4h", origin="epoch", label="left", closed="left")
    ):
        expected = pd.date_range(bucket_start, periods=4, freq="h")
        if len(group) != 4 or not group.index.equals(expected):
            continue
        bucket_end = bucket_start + pd.Timedelta(hours=4)
        if bucket_end > now_ts:
            continue
        row = {
            "Open": float(group["Open"].iloc[0]),
            "High": float(group["High"].max()),
            "Low": float(group["Low"].min()),
            "Close": float(group["Close"].iloc[-1]),
        }
        if "Volume" in group.columns:
            row["Volume"] = float(group["Volume"].sum())
        rows.append(row)
        labels.append(bucket_end)
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close"], index=pd.DatetimeIndex([], tz="UTC"))
    result = pd.DataFrame(rows, index=pd.DatetimeIndex(labels))
    result.index.name = "Datetime"
    return result

def calculate_net_rr(direction: str, entry: float, stop: float, target: float, round_trip_cost_price: float | None) -> dict[str, float | None]:
    """Calculate directional R/R after round-trip costs expressed in price units."""
    values = (entry, stop, target)
    if not all(np.isfinite(value) and value > 0 for value in values):
        return {"gross_rr": None, "net_rr": None}
    if round_trip_cost_price is None or not np.isfinite(round_trip_cost_price) or round_trip_cost_price < 0:
        return {"gross_rr": None, "net_rr": None}
    if direction == "bullish":
        risk, reward = entry - stop, target - entry
    elif direction == "bearish":
        risk, reward = stop - entry, entry - target
    else:
        return {"gross_rr": None, "net_rr": None}
    if risk <= 0 or reward <= 0:
        return {"gross_rr": None, "net_rr": None}
    gross_rr = reward / risk
    net_reward = reward - round_trip_cost_price
    net_risk = risk + round_trip_cost_price
    net_rr = net_reward / net_risk if net_reward > 0 and net_risk > 0 else None
    return {
        "gross_rr": round(float(gross_rr), 6),
        "net_rr": round(float(net_rr), 6) if net_rr is not None else None,
    }


def _setup_signal(hourly: pd.DataFrame, direction: str, atr: float) -> str | None:
    if len(hourly) < 30 or atr is None or not np.isfinite(atr) or atr <= 0:
        return None
    data = hourly
    close, high, low = data["Close"], data["High"], data["Low"]
    ema20 = close.ewm(span=20, adjust=False).mean()
    last = data.iloc[-1]
    prior_high = float(high.iloc[-21:-1].max())
    prior_low = float(low.iloc[-21:-1].min())
    pad = 0.20 * atr

    if direction == "bullish":
        if bool((low.iloc[-4:-1] <= ema20.iloc[-4:-1] + pad).any()) and float(last["Close"]) > float(ema20.iloc[-1]) and float(last["Close"]) > float(last["Open"]):
            return "trend_pullback"
        if float(low.iloc[-4:].min()) <= prior_high + pad and float(last["Close"]) > prior_high:
            return "breakout_retest"
        if float(last["Low"]) <= prior_low + pad and float(last["Close"]) > float(last["Low"]) + 0.6 * (float(last["High"]) - float(last["Low"])):
            return "range_rejection"
    else:
        if bool((high.iloc[-4:-1] >= ema20.iloc[-4:-1] - pad).any()) and float(last["Close"]) < float(ema20.iloc[-1]) and float(last["Close"]) < float(last["Open"]):
            return "trend_pullback"
        if float(high.iloc[-4:].max()) >= prior_low - pad and float(last["Close"]) < prior_low:
            return "breakout_retest"
        if float(last["High"]) >= prior_high - pad and float(last["Close"]) < float(last["High"]) - 0.6 * (float(last["High"]) - float(last["Low"])):
            return "range_rejection"
    return None


def _nearest_structural_target(frame: pd.DataFrame, direction: str, entry: float) -> float | None:
    if len(frame) < 10:
        return None
    window = frame.iloc[-60:-1] if len(frame) > 60 else frame.iloc[:-1]
    if window.empty:
        return None
    if direction == "bullish":
        levels = window.loc[(window["High"] > entry) & (window["High"].shift(1) <= window["High"]) & (window["High"].shift(-1) <= window["High"]), "High"]
        return float(levels.min()) if not levels.empty else None
    levels = window.loc[(window["Low"] < entry) & (window["Low"].shift(1) >= window["Low"]) & (window["Low"].shift(-1) >= window["Low"]), "Low"]
    return float(levels.max()) if not levels.empty else None


def build_opportunity(
    symbol: str,
    frames: dict[str, pd.DataFrame],
    settings: dict,
    *,
    costs: dict[str, float] | None = None,
    evidence: dict[str, Any] | None = None,
    quote_timestamp: str | None = None,
    analysis_cutoff_utc: str | None = None,
    instrument: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a fully traceable candidate; missing execution inputs prevent active status."""
    evidence = evidence or {}
    cutoff = analysis_cutoff_utc or datetime.now(timezone.utc).isoformat()
    frames = dict(frames)
    frames["1h"] = completed_hourly_candles(frames.get("1h"))
    cleaned_frames = {tf: _clean_ohlc(frames.get(tf)) for tf in TIMEFRAMES}
    analyses = {tf: analyze(cleaned_frames[tf], settings) for tf in TIMEFRAMES}
    quality_flags = []
    last_closed_candles = {}
    for tf in TIMEFRAMES:
        original = frames.get(tf)
        clean = cleaned_frames[tf]
        last_closed_candles[tf] = clean.index[-1].isoformat() if not clean.empty else None
        if original is None or original.empty:
            quality_flags.append(f"{tf}_ohlc_missing")
        elif len(clean) < len(original):
            quality_flags.append(f"{tf}_invalid_or_duplicate_ohlc_rows_removed")
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "analysis_cutoff_utc": cutoff,
        "quote_timestamp": quote_timestamp,
        "instrument": instrument or {},
        "timeframes": analyses,
        "last_candle_index_utc": {
            tf: frames[tf].index[-1].isoformat() if frames.get(tf) is not None and not frames[tf].empty else None
            for tf in TIMEFRAMES
        },
        "direction": None,
        "setup_type": None,
        "status": "unrankable",
        "entry_zone": None,
        "entry_trigger": None,
        "stop_loss": None,
        "targets": [],
        "invalidation": None,
        "expires_at": None,
        "gross_rr": None,
        "net_rr": None,
        "stop_rationale": None,
        "estimated_costs": costs,
        "event_risk": None,
        "score_raw": None,
        "score_adjusted": None,
        "score_components": {},
        "missing_evidence": [],
        "risk_flags": [],
    }
    if any(analyses[tf].get("status") != "ok" for tf in TIMEFRAMES):
        result["missing_evidence"].append("insufficient_or_invalid_ohlc_for_1d_4h_1h")
        return result
    directions = [analyses[tf]["direction"] for tf in TIMEFRAMES]
    if directions[0] not in ("bullish", "bearish") or len(set(directions)) != 1:
        result["status"] = "watchlist"
        result["risk_flags"].append("multi_timeframe_direction_not_aligned")
        return result

    direction = directions[0]
    hourly = cleaned_frames["1h"]
    four = cleaned_frames["4h"]
    signal = _setup_signal(hourly, direction, float(analyses["1h"]["atr"]))
    if signal is None:
        result["status"] = "watchlist"
        result["direction"] = direction
        result["risk_flags"].append("no_confirmed_1h_setup_trigger")
        return result

    entry = float(hourly["Close"].iloc[-1])
    atr = float(analyses["1h"]["atr"])
    stop_buffer = float(settings.get("risk", {}).get("stop_atr_buffer", 0.2)) * atr
    lookback = hourly.iloc[-20:-1]
    stop = float(lookback["Low"].min() - stop_buffer) if direction == "bullish" else float(lookback["High"].max() + stop_buffer)
    risk = entry - stop if direction == "bullish" else stop - entry
    target = _nearest_structural_target(four, direction, entry)
    result.update({
        "direction": direction,
        "setup_type": signal,
        "entry_zone": {"low": entry - 0.1 * atr, "high": entry + 0.1 * atr},
        "entry_trigger": {"type": "confirmed_1h_close", "close": entry, "timestamp": hourly.index[-1].isoformat()},
        "stop_loss": stop,
        "stop_rationale": "20-candle 1H swing extreme plus configured ATR buffer",
        "invalidation": {"type": "1h_close_beyond_stop", "price": stop},
        "expires_at": (hourly.index[-1] + pd.Timedelta(hours=4)).isoformat(),
    })
    if risk <= 0 or target is None:
        result["status"] = "watchlist"
        result["risk_flags"].append("no_valid_structural_stop_or_target")
        return result
    reward = target - entry if direction == "bullish" else entry - target
    gross_rr = reward / risk if reward > 0 else None
    result["targets"] = [{"price": target, "allocation_pct": 100, "basis": "nearest_confirmed_4h_swing"}]
    result["gross_rr"] = round(gross_rr, 3) if gross_rr is not None else None
    costs_available = (
        costs is not None
        and isinstance(costs.get("round_trip_cost_price"), (int, float))
        and costs["round_trip_cost_price"] >= 0
    )
    if costs_available:
        rr_values = calculate_net_rr(
            direction, entry, stop, target, float(costs["round_trip_cost_price"])
        )
        result["gross_rr"] = rr_values["gross_rr"]
        result["net_rr"] = rr_values["net_rr"]
        net_rr = result["net_rr"]
        if net_rr is None or net_rr < float(settings.get("risk", {}).get("minimum_net_rr", 2.0)):
            result["status"] = "watchlist"
            result["risk_flags"].append("net_rr_below_configured_minimum")
            return result
    else:
        result["missing_evidence"].append("instrument_specific_round_trip_cost_not_configured")
        result["risk_flags"].append("net_rr_unavailable_cost_unknown")

    required_evidence = ("fundamental_score", "news_score", "liquidity_score", "data_quality_score", "independent_evidence_score")
    missing = [key for key in required_evidence if not isinstance(evidence.get(key), (int, float))]
    result["missing_evidence"].extend(missing)
    result["status"] = "active" if costs_available and not missing else "conditional"

    ranking = settings.get("ranking", {})
    weights = ranking.get("weights", {
        "technical": 25, "net_rr": 20, "fundamental": 15, "news": 10,
        "data_quality": 15, "independent_evidence": 10, "liquidity": 5,
    })
    components = {
        "technical": float(np.mean([analyses[tf]["score"] for tf in TIMEFRAMES])),
        "net_rr": min(100.0, max(0.0, float(result["net_rr"]) / 3.0 * 100.0)) if isinstance(result.get("net_rr"), (int, float)) else None,
        "fundamental": evidence.get("fundamental_score"),
        "news": evidence.get("news_score"),
        "data_quality": evidence.get("data_quality_score"),
        "independent_evidence": evidence.get("independent_evidence_score"),
        "liquidity": evidence.get("liquidity_score"),
    }
    available = {key: float(value) for key, value in components.items() if isinstance(value, (int, float))}
    denom = sum(float(weights[key]) for key in available)
    raw = sum(available[key] * float(weights[key]) for key in available) / denom if denom else None
    result["score_components"] = components
    result["score_raw"] = round(raw, 2) if raw is not None else None
    result["score_adjusted"] = result["score_raw"]
    result["score_coverage"] = sorted(available)
    result["score_method"] = "weighted_available_components_renormalized; not probability; incomplete coverage cannot be active"
    return result


def rank_opportunities(
    items: list[dict[str, Any]],
    max_items: int = 10,
    returns_by_symbol: dict[str, pd.Series] | None = None,
    correlation_threshold: float = 0.85,
    correlation_penalty_points: float = 10.0,
) -> dict[str, Any]:
    """Rank active opportunities with a transparent, optional return-correlation penalty."""
    active = [
        item for item in items
        if item.get("status") == "active"
        and isinstance(item.get("score_raw", item.get("score_adjusted")), (int, float))
    ]
    active.sort(key=lambda item: float(item.get("score_raw", item.get("score_adjusted"))), reverse=True)
    selected: list[dict[str, Any]] = []
    checked = 0
    unavailable = 0
    total_penalty = 0.0

    for source in active:
        item = dict(source)
        raw_score = float(item.get("score_raw", item.get("score_adjusted")))
        series = (returns_by_symbol or {}).get(item.get("symbol"))
        correlations = []
        if isinstance(series, pd.Series):
            for prior in selected:
                prior_series = (returns_by_symbol or {}).get(prior.get("symbol"))
                if not isinstance(prior_series, pd.Series):
                    continue
                aligned = pd.concat([series.rename("candidate"), prior_series.rename("prior")], axis=1).dropna()
                if len(aligned) >= 30 and aligned["candidate"].std() > 0 and aligned["prior"].std() > 0:
                    correlations.append(abs(float(aligned["candidate"].corr(aligned["prior"]))))
        if not selected:
            # The first selected opportunity has no higher-ranked peer to compare.
            item["max_abs_correlation_to_higher_ranked"] = None
            item["diversification_penalty_points"] = 0.0
            item["score_adjusted"] = round(raw_score, 2)
        elif correlations:
            checked += 1
            maximum = max(correlations)
            excess = max(0.0, maximum - correlation_threshold) / max(1e-9, 1.0 - correlation_threshold)
            penalty = min(correlation_penalty_points, correlation_penalty_points * excess)
            item["max_abs_correlation_to_higher_ranked"] = round(maximum, 4)
            item["diversification_penalty_points"] = round(penalty, 2)
            item["score_adjusted"] = round(max(0.0, raw_score - penalty), 2)
            if penalty:
                item.setdefault("risk_flags", []).append("high_correlation_with_higher_ranked_opportunity")
            total_penalty += penalty
        else:
            unavailable += 1
            item["max_abs_correlation_to_higher_ranked"] = None
            item["diversification_penalty_points"] = None
            item["score_adjusted"] = round(raw_score, 2)
            item.setdefault("risk_flags", []).append("correlation_check_unavailable")
        selected.append(item)

    selected.sort(key=lambda item: float(item.get("score_adjusted", 0.0)), reverse=True)
    selected = selected[:max(0, min(int(max_items), 10))]
    return {
        "schema_version": SCHEMA_VERSION,
        "ranked_at_utc": datetime.now(timezone.utc).isoformat(),
        "count": len(selected),
        "opportunities": [{**item, "rank": rank} for rank, item in enumerate(selected, 1)],
        "conditional_count": sum(item.get("status") == "conditional" for item in items),
        "watchlist_count": sum(item.get("status") == "watchlist" for item in items),
        "unrankable_count": sum(item.get("status") == "unrankable" for item in items),
        "correlation_checked_count": checked,
        "correlation_unavailable_count": unavailable,
        "total_diversification_penalty_points": round(total_penalty, 2),
        "note": "Only active opportunities are ranked; fewer than ten is valid. Score is not win probability. Correlation penalty is separate from raw score.",
    }
