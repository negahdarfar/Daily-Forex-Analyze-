"""Cost-aware, timestamp-safe evaluator for precomputed trading signals.

This is a research evaluator, not a broker fill simulator. Signals must be
created only from information available at signal_time. Outcomes use bars
strictly after that timestamp, with optional holding windows and overlap control.
"""
from __future__ import annotations

import math
import pandas as pd


def evaluate_signals(
    signals: pd.DataFrame,
    forward_returns: pd.Series,
    min_trades: int = 30,
    *,
    spread_bps: float = 0.0,
    commission_bps: float = 0.0,
    slippage_bps: float = 0.0,
    max_holding_bars: int = 1,
    allow_overlapping: bool = False,
) -> dict:
    required = {"signal", "signal_time"}
    if signals is None or signals.empty or not required.issubset(signals.columns):
        return {"status": "invalid_input", "trade_count": 0}
    if not isinstance(forward_returns, pd.Series) or not isinstance(forward_returns.index, pd.DatetimeIndex):
        return {"status": "invalid_returns", "trade_count": 0}
    costs = (spread_bps, commission_bps, slippage_bps)
    if any(not isinstance(x, (int, float)) or not math.isfinite(float(x)) or float(x) < 0 for x in costs):
        return {"status": "invalid_costs", "trade_count": 0}
    if int(max_holding_bars) < 1 or int(min_trades) < 1:
        return {"status": "invalid_parameters", "trade_count": 0}

    rows = signals.copy()
    rows["signal_time"] = pd.to_datetime(rows["signal_time"], utc=True, errors="coerce")
    rows = rows.dropna(subset=["signal_time"])
    rows = rows[rows["signal"].isin([-1, 1])].sort_values("signal_time")
    returns = pd.to_numeric(forward_returns, errors="coerce").dropna().copy()
    if returns.index.tz is None:
        returns.index = returns.index.tz_localize("UTC")
    else:
        returns.index = returns.index.tz_convert("UTC")
    returns = returns[~returns.index.duplicated(keep="last")].sort_index()
    if returns.empty:
        return {"status": "no_matched_outcomes", "trade_count": 0}

    outcomes, gross_outcomes = [], []
    skipped_overlapping = 0
    last_exit_position = -1
    return_index = returns.index
    values = returns.to_numpy(dtype=float)
    for row in rows.itertuples(index=False):
        # Strictly next bar: a signal cannot earn the return of its own candle.
        position = int(return_index.searchsorted(row.signal_time, side="right"))
        if position >= len(values):
            continue
        end_position = min(len(values), position + int(max_holding_bars))
        if not allow_overlapping and position <= last_exit_position:
            skipped_overlapping += 1
            continue
        window = values[position:end_position]
        if len(window) == 0:
            continue
        gross = math.prod(1.0 + float(row.signal) * float(value) for value in window) - 1.0
        total_cost_bps = float(spread_bps) + float(commission_bps) + float(slippage_bps)
        net = (1.0 + gross) * (1.0 - total_cost_bps / 10000.0) - 1.0
        gross_outcomes.append(gross)
        outcomes.append(net)
        last_exit_position = end_position - 1

    if not outcomes:
        return {"status": "no_matched_outcomes", "trade_count": 0,
                "skipped_overlapping": skipped_overlapping}
    wins = [x for x in outcomes if x > 0]
    losses = [x for x in outcomes if x < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    equity, peak, max_dd = 1.0, 1.0, 0.0
    for result in outcomes:
        equity *= max(0.0, 1.0 + result)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak else 0.0)
    expectancy = sum(outcomes) / len(outcomes)
    return {
        "status": "evaluated" if len(outcomes) >= min_trades else "insufficient_sample",
        "trade_count": len(outcomes),
        "skipped_overlapping": skipped_overlapping,
        "win_rate_pct": round(100 * len(wins) / len(outcomes), 2),
        "gross_expectancy_per_trade": round(sum(gross_outcomes) / len(gross_outcomes), 6),
        "expectancy_per_trade": round(expectancy, 6),
        "net_expectancy_per_trade": round(expectancy, 6),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else (None if not gross_profit else "infinite"),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sample_threshold": min_trades,
        "costs_bps": {"spread": float(spread_bps), "commission": float(commission_bps),
                      "slippage": float(slippage_bps), "total": total_cost_bps},
        "holding_bars": int(max_holding_bars),
        "overlapping_trades_allowed": bool(allow_overlapping),
        "warning": "Research evaluator only, not a broker fill simulator. Validate bid/ask fills, stop/target intrabar ordering, financing, gaps, venue hours, contract sizing and strict out-of-sample splits before deployment.",
    }
