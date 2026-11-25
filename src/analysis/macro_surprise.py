"""Standardized macro surprise calculations with explicit missing-data handling."""
from __future__ import annotations
import math


def standardized_surprise(actual: float | None, consensus: float | None, historical_surprises: list[float] | None = None) -> dict:
    if actual is None or consensus is None:
        return {"status": "missing", "surprise": None, "z_score": None}
    actual, consensus = float(actual), float(consensus)
    surprise = actual - consensus
    history = [float(x) for x in (historical_surprises or []) if x is not None and math.isfinite(float(x))]
    if len(history) < 8:
        return {"status": "available_unstandardized", "surprise": surprise, "z_score": None,
                "sample_count": len(history), "note": "At least 8 historical comparable releases are required for z-score."}
    mean = sum(history) / len(history)
    variance = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
    std = math.sqrt(variance)
    return {"status": "available", "surprise": surprise,
            "z_score": round((surprise - mean) / std, 4) if std > 0 else None,
            "sample_count": len(history), "note": "Compare like-for-like releases and preserve units/revisions."}
