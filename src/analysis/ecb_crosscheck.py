"""Daily ECB reference-rate cross-check against Yahoo FX close histories.

ECB rates are official daily reference values, not intraday executable quotes.
The result is diagnostic only and never replaces the primary market series.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


CURRENCIES = ("USD", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD")


def build_ecb_fx_cross_checks(
    results: list[dict[str, Any]],
    ecb_payload: dict[str, Any] | None,
    discrepancy_threshold_pct: float = 0.75,
) -> dict[str, Any]:
    rows = (ecb_payload or {}).get("observations", [])
    per_eur: dict[str, float] = {"EUR": 1.0}
    timestamps: dict[str, str] = {}
    for row in rows:
        code = str(row.get("currency", "")).upper()
        value = row.get("value")
        if code in CURRENCIES and isinstance(value, (int, float)) and float(value) > 0:
            per_eur[code] = float(value)
            timestamps[code] = str(row.get("data_timestamp", ""))
    result_by_symbol = {str(row.get("asset", "")).upper(): row for row in results}
    checks = []
    for symbol, primary in sorted(result_by_symbol.items()):
        if len(symbol) != 6 or symbol[:3] not in per_eur or symbol[3:] not in per_eur:
            continue
        quote_reference = per_eur[symbol[:3]] / per_eur[symbol[3:]]
        primary_close = (primary.get("analysis") or {}).get("close")
        if not isinstance(primary_close, (int, float)) or float(primary_close) <= 0:
            continue
        diff_pct = (float(primary_close) / quote_reference - 1.0) * 100.0
        checks.append({
            "symbol": symbol,
            "primary_provider": primary.get("provider", "Yahoo Finance"),
            "primary_close": float(primary_close),
            "ecb_reference_rate": round(quote_reference, 8),
            "ecb_reference_date": min(
                [timestamps.get(symbol[:3]), timestamps.get(symbol[3:])],
                key=lambda x: x or "9999",
            ),
            "difference_pct": round(diff_pct, 4),
            "status": "large_reference_gap" if abs(diff_pct) >= float(discrepancy_threshold_pct) else "within_reference_band",
            "reference_type": "official_daily_ECB_reference_not_executable_spot",
        })
    return {
        "status": "available" if checks else "insufficient_reference_coverage",
        "source": "European Central Bank",
        "coverage_pairs": len(checks),
        "discrepancy_threshold_pct": float(discrepancy_threshold_pct),
        "checks": checks,
        "source_url": "https://data-api.ecb.europa.eu/service/data/EXR/",
        "methodology": "ECB currencies-per-EUR observations are cross-divided to derive pair reference rates; compared with Yahoo daily close. Date/time mismatch and reference-vs-market differences are expected; this is a diagnostic, not a second intraday feed.",
        "live_execution_eligible": False,
    }
