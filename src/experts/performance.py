"""Metrics from closed, independently verified trades only."""
from __future__ import annotations
from math import isfinite


def realized_r_multiple(direction: str, entry: float, stop_loss: float, exit_price: float, fees_r: float = 0.0) -> float:
    risk = abs(float(entry) - float(stop_loss))
    if risk <= 0:
        raise ValueError("Entry and stop-loss must define positive initial risk.")
    side = direction.strip().lower()
    if side in {"long", "buy", "bullish"}:
        gross_r = (float(exit_price) - float(entry)) / risk
    elif side in {"short", "sell", "bearish"}:
        gross_r = (float(entry) - float(exit_price)) / risk
    else:
        raise ValueError("direction must be long/buy/bullish or short/sell/bearish")
    return gross_r - float(fees_r)


def calculate_performance(realized_r: list[float], minimum_sample: int = 30) -> dict:
    values = [float(value) for value in realized_r if isfinite(float(value))]
    n = len(values)
    if not n:
        return {"status": "no_verified_closed_trades", "sample_size": 0,
                "win_rate": None, "expectancy_r": None, "profit_factor": None,
                "max_drawdown_r": None, "average_r": None, "ranking_eligible": False}
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else None
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    expectancy = sum(values) / n
    eligible = n >= int(minimum_sample)
    return {
        "status": "measured" if eligible else "insufficient_sample",
        "sample_size": n, "win_rate": round(len(wins) / n * 100, 2),
        "expectancy_r": round(expectancy, 4),
        "profit_factor": round(pf, 4) if pf is not None else None,
        "profit_factor_status": "defined" if pf is not None else "undefined_no_losses",
        "max_drawdown_r": round(drawdown, 4), "average_r": round(expectancy, 4),
        "ranking_eligible": eligible and expectancy > 0 and pf is not None
    }


def assess_trader_history(trades: list[dict], minimum_sample: int = 30) -> dict:
    verified = [float(t["realized_r"]) for t in trades
                if t.get("verification_status") == "independently_verified"
                and t.get("realized_r") not in (None, "")]
    metrics = calculate_performance(verified, minimum_sample)
    metrics["excluded_unverified_count"] = len(trades) - len(verified)
    metrics["warning"] = "Only closed independently verified trades are included; source authenticity still requires audit."
    return metrics
