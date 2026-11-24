"""Small deterministic walk-forward evaluator for precomputed, timestamped signals.

Signals must be generated using information available at signal_time. Returns are
measured only after that timestamp. This module does not create trading signals.
"""
from __future__ import annotations
import math
import pandas as pd


def evaluate_signals(signals: pd.DataFrame, forward_returns: pd.Series, min_trades: int = 30) -> dict:
    required = {"signal", "signal_time"}
    if signals is None or signals.empty or not required.issubset(signals.columns):
        return {"status": "invalid_input", "trade_count": 0}
    if not isinstance(forward_returns, pd.Series) or not isinstance(forward_returns.index, pd.DatetimeIndex):
        return {"status": "invalid_returns", "trade_count": 0}
    rows = signals.copy()
    rows["signal_time"] = pd.to_datetime(rows["signal_time"], utc=True, errors="coerce")
    rows = rows.dropna(subset=["signal_time"])
    rows = rows[rows["signal"].isin([-1, 1])]
    returns = pd.to_numeric(forward_returns, errors="coerce").dropna().copy()
    if returns.index.tz is None:
        returns.index = returns.index.tz_localize("UTC")
    else:
        returns.index = returns.index.tz_convert("UTC")
    outcomes = []
    for row in rows.itertuples(index=False):
        # Use the first return observation strictly after the signal timestamp.
        future = returns.loc[returns.index > row.signal_time]
        if future.empty:
            continue
        outcomes.append(float(row.signal) * float(future.iloc[0]))
    if not outcomes:
        return {"status": "no_matched_outcomes", "trade_count": 0}
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
        "win_rate_pct": round(100 * len(wins) / len(outcomes), 2),
        "expectancy_per_trade": round(expectancy, 6),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else (None if not gross_profit else "infinite"),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sample_threshold": min_trades,
        "warning": "Illustrative evaluator only: include spread, commission, slippage, financing, overlapping trades and strict out-of-sample splits before interpreting results.",
    }
