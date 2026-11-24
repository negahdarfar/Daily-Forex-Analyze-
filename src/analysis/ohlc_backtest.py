"""Conservative OHLC paper backtester for timestamped, precomputed signals.

Entry is the next candle open after publication. If stop and target are both
inside one candle, stop is assumed first. This is deliberately conservative.
It is not a broker emulator: use bid/ask tick data and instrument-specific
contract specifications before treating results as deployable.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd


def backtest_ohlc_signals(
    signals: pd.DataFrame,
    candles_by_symbol: dict[str, pd.DataFrame],
    *,
    initial_equity: float = 10_000.0,
    risk_fraction: float = 0.01,
    spread_bps: float = 0.0,
    commission_bps: float = 0.0,
    slippage_bps: float = 0.0,
    max_holding_bars: int = 48,
    allow_overlapping_per_symbol: bool = False,
) -> dict[str, Any]:
    required = {"symbol", "signal_time", "direction", "stop_loss", "take_profit"}
    if signals is None or signals.empty or not required.issubset(signals.columns):
        return {"status": "invalid_input", "trades": [], "trade_count": 0}
    if initial_equity <= 0 or not 0 < risk_fraction <= 0.05 or max_holding_bars < 1:
        return {"status": "invalid_parameters", "trades": [], "trade_count": 0}
    costs = (spread_bps, commission_bps, slippage_bps)
    if any(not math.isfinite(float(x)) or float(x) < 0 for x in costs):
        return {"status": "invalid_costs", "trades": [], "trade_count": 0}

    rows = signals.copy()
    rows["signal_time"] = pd.to_datetime(rows["signal_time"], utc=True, errors="coerce")
    rows = rows.dropna(subset=["signal_time"]).sort_values("signal_time")
    normalized: dict[str, pd.DataFrame] = {}
    for symbol, frame in (candles_by_symbol or {}).items():
        if frame is None or frame.empty or not {"Open", "High", "Low", "Close"}.issubset(frame.columns):
            continue
        clean = frame.copy()
        clean.index = pd.to_datetime(clean.index, utc=True, errors="coerce")
        clean = clean.loc[~clean.index.isna()].sort_index()
        clean = clean[~clean.index.duplicated(keep="last")]
        for col in ("Open", "High", "Low", "Close"):
            clean[col] = pd.to_numeric(clean[col], errors="coerce")
        clean = clean.dropna(subset=["Open", "High", "Low", "Close"])
        if (clean["High"] < clean["Low"]).any():
            continue
        normalized[str(symbol)] = clean

    equity = float(initial_equity)
    peak = equity
    max_drawdown = 0.0
    total_cost_bps = sum(float(x) for x in costs)
    last_exit: dict[str, int] = {}
    trades: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}

    for row in rows.itertuples(index=False):
        symbol = str(row.symbol)
        frame = normalized.get(symbol)
        if frame is None:
            skipped["missing_or_invalid_candles"] = skipped.get("missing_or_invalid_candles", 0) + 1
            continue
        direction = str(row.direction).lower()
        if direction not in {"bullish", "bearish", "long", "short"}:
            skipped["invalid_direction"] = skipped.get("invalid_direction", 0) + 1
            continue
        side = 1.0 if direction in {"bullish", "long"} else -1.0
        try:
            stop = float(row.stop_loss)
            target = float(row.take_profit)
        except (TypeError, ValueError):
            skipped["invalid_levels"] = skipped.get("invalid_levels", 0) + 1
            continue
        idx = frame.index
        entry_pos = int(idx.searchsorted(row.signal_time, side="right"))
        if entry_pos >= len(frame):
            skipped["no_post_signal_bar"] = skipped.get("no_post_signal_bar", 0) + 1
            continue
        if not allow_overlapping_per_symbol and entry_pos <= last_exit.get(symbol, -1):
            skipped["overlapping"] = skipped.get("overlapping", 0) + 1
            continue

        entry_time = idx[entry_pos]
        entry_raw = float(frame.iloc[entry_pos]["Open"])
        if not math.isfinite(entry_raw) or entry_raw <= 0:
            skipped["invalid_entry"] = skipped.get("invalid_entry", 0) + 1
            continue
        if (side > 0 and not stop < entry_raw < target) or (side < 0 and not target < entry_raw < stop):
            skipped["invalid_level_geometry"] = skipped.get("invalid_level_geometry", 0) + 1
            continue
        risk_per_unit = abs(entry_raw - stop)
        risk_cash = equity * float(risk_fraction)
        units = risk_cash / risk_per_unit
        exit_price = None
        exit_time = None
        exit_reason = "time_exit"
        end_pos = min(len(frame), entry_pos + int(max_holding_bars))
        for pos in range(entry_pos, end_pos):
            candle = frame.iloc[pos]
            op, hi, lo, cl = (float(candle[k]) for k in ("Open", "High", "Low", "Close"))
            if side > 0:
                if op <= stop:
                    exit_price, exit_reason = op, "stop_gap"
                elif op >= target:
                    exit_price, exit_reason = op, "target_gap"
                elif lo <= stop:
                    exit_price, exit_reason = stop, "stop"
                elif hi >= target:
                    exit_price, exit_reason = target, "target"
            else:
                if op >= stop:
                    exit_price, exit_reason = op, "stop_gap"
                elif op <= target:
                    exit_price, exit_reason = op, "target_gap"
                elif hi >= stop:
                    exit_price, exit_reason = stop, "stop"
                elif lo <= target:
                    exit_price, exit_reason = target, "target"
            if exit_price is not None:
                exit_time = idx[pos]
                last_exit[symbol] = pos
                break
        if exit_price is None:
            pos = end_pos - 1
            exit_price = float(frame.iloc[pos]["Close"])
            exit_time = idx[pos]
            last_exit[symbol] = pos
        gross_pnl = side * (float(exit_price) - entry_raw) * units
        notional = ((entry_raw + float(exit_price)) / 2.0) * units
        transaction_cost = notional * total_cost_bps / 10_000.0
        net_pnl = gross_pnl - transaction_cost
        realized_r = net_pnl / risk_cash if risk_cash else 0.0
        equity_before = equity
        equity = max(0.0, equity + net_pnl)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak else 0.0)
        trades.append({
            "symbol": symbol, "direction": direction,
            "signal_time": row.signal_time.isoformat(),
            "entry_time": entry_time.isoformat(), "entry_price": entry_raw,
            "exit_time": exit_time.isoformat(), "exit_price": float(exit_price),
            "exit_reason": exit_reason, "stop_loss": stop, "take_profit": target,
            "units": round(units, 6), "risk_cash": round(risk_cash, 2),
            "gross_pnl": round(gross_pnl, 2), "transaction_cost": round(transaction_cost, 2),
            "net_pnl": round(net_pnl, 2), "realized_r": round(realized_r, 4),
            "equity_before": round(equity_before, 2), "equity_after": round(equity, 2),
            "same_candle_stop_target_policy": "stop_first_conservative",
        })

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] < 0]
    gross_profit = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))
    count = len(trades)
    return {
        "status": "evaluated" if count else "no_executable_signals",
        "initial_equity": round(initial_equity, 2),
        "final_equity": round(equity, 2),
        "net_return_pct": round((equity / initial_equity - 1) * 100, 3),
        "trade_count": count,
        "win_rate_pct": round(len(wins) / count * 100, 2) if count else None,
        "expectancy_r": round(sum(t["realized_r"] for t in trades) / count, 4) if count else None,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "max_drawdown_pct": round(max_drawdown * 100, 3),
        "costs_bps": {"spread": float(spread_bps), "commission": float(commission_bps),
                      "slippage": float(slippage_bps), "total": total_cost_bps},
        "risk_fraction_per_trade": float(risk_fraction),
        "max_holding_bars": int(max_holding_bars),
        "skipped_signals": skipped,
        "trades": trades,
        "warning": "OHLC research/paper simulator only. Next-bar-open entries, conservative stop-first same-bar ordering, fixed bps costs and no margin/lot-size/financing/swap or broker-specific bid-ask model. Tick/bid-ask validation and out-of-sample tests are mandatory before deployment.",
    }
