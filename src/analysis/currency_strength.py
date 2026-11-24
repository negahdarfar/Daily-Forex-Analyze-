"""Cross-sectional currency strength from aligned FX close series.

Input prices must be timestamp-indexed, completed bars from comparable sources.
Strength is a descriptive relative-return measure, not a trade signal.
"""
from __future__ import annotations

from typing import Mapping
import numpy as np
import pandas as pd

CURRENCIES = ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD")


def calculate_currency_strength(
    pair_closes: Mapping[str, pd.Series],
    lookback: int = 20,
    min_pairs_per_currency: int = 2,
) -> dict:
    if lookback < 1 or min_pairs_per_currency < 1:
        raise ValueError("lookback and min_pairs_per_currency must be positive")
    contributions: dict[str, list[float]] = {c: [] for c in CURRENCIES}
    used_pairs: list[str] = []
    for symbol, series in pair_closes.items():
        symbol = str(symbol).upper().replace("/", "")
        if len(symbol) != 6 or symbol[:3] not in CURRENCIES or symbol[3:] not in CURRENCIES:
            continue
        if not isinstance(series, pd.Series):
            continue
        clean = pd.to_numeric(series, errors="coerce").dropna()
        clean = clean[clean > 0]
        if len(clean) <= lookback:
            continue
        change = float(clean.iloc[-1] / clean.iloc[-lookback - 1] - 1.0)
        if not np.isfinite(change):
            continue
        contributions[symbol[:3]].append(change * 100.0)
        contributions[symbol[3:]].append(-change * 100.0)
        used_pairs.append(symbol)
    rows = {}
    for currency, values in contributions.items():
        rows[currency] = {
            "strength_pct": round(float(np.mean(values)), 5) if len(values) >= min_pairs_per_currency else None,
            "pair_count": len(values),
            "status": "available" if len(values) >= min_pairs_per_currency else "insufficient_pair_coverage",
        }
    available = [r["strength_pct"] for r in rows.values() if r["strength_pct"] is not None]
    if available:
        center = float(np.mean(available))
        for row in rows.values():
            if row["strength_pct"] is not None:
                row["relative_score"] = round(float(np.clip(50 + (row["strength_pct"] - center) * 5, 0, 100)), 2)
            else:
                row["relative_score"] = None
    else:
        for row in rows.values():
            row["relative_score"] = None
    ranked = sorted(
        ((c, r["relative_score"]) for c, r in rows.items() if r["relative_score"] is not None),
        key=lambda x: x[1], reverse=True,
    )
    return {
        "status": "available" if ranked else "insufficient_data",
        "lookback_bars": lookback,
        "pairs_used": sorted(set(used_pairs)),
        "coverage_pairs": len(set(used_pairs)),
        "currencies": rows,
        "strongest": ranked[0][0] if ranked else None,
        "weakest": ranked[-1][0] if ranked else None,
        "method": "mean_signed_pair_percent_return; cross-sectional normalization",
        "warning": "Not a probability or standalone entry signal; coverage and source consistency matter.",
    }
