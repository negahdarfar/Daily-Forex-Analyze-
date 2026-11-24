"""Auditable, manually verified expert trade ledger.

The module never treats a public forecast, follower count or self-asserted P/L
as verified. Each record must reference a closed trade and an independent
verification artifact reviewed by someone other than the analyst.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from src.experts.performance import calculate_performance, realized_r_multiple


def _valid_time(value: Any) -> bool:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return False
        return stamp.astimezone(timezone.utc) <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


def validate_verified_trade(record: dict[str, Any]) -> tuple[bool, str, float | None]:
    required = ("trade_id", "analyst_id", "symbol", "direction", "entry",
                "stop_loss", "exit_price", "closed_at", "source_url",
                "verification_status", "verified_by", "verified_at",
                "evidence_reference")
    missing = [key for key in required if record.get(key) in (None, "")]
    if missing:
        return False, "missing:" + ",".join(missing), None
    if record.get("verification_status") != "independently_verified":
        return False, "not_independently_verified", None
    if str(record["verified_by"]).strip().casefold() == str(record["analyst_id"]).strip().casefold():
        return False, "self_verification_rejected", None
    if not _valid_time(record["closed_at"]) or not _valid_time(record["verified_at"]):
        return False, "invalid_or_future_timestamp", None
    source_url = str(record["source_url"]).strip().lower()
    if not source_url.startswith(("https://", "http://")):
        return False, "invalid_source_url", None
    try:
        r_value = realized_r_multiple(
            str(record["direction"]), float(record["entry"]),
            float(record["stop_loss"]), float(record["exit_price"]),
            float(record.get("fees_r", 0.0)),
        )
    except (TypeError, ValueError, ZeroDivisionError):
        return False, "invalid_trade_prices_or_direction", None
    if not isfinite(r_value):
        return False, "non_finite_realized_r", None
    return True, "verified_record_shape", r_value


def build_verified_expert_evidence(
    analysis_candidates: list[dict[str, Any]],
    ledger: dict[str, Any] | list[dict[str, Any]] | None,
    minimum_sample: int = 30,
) -> dict[str, dict[str, Any]]:
    """Join registered named analysts to independently reviewed closed-trade records."""
    trades = ledger.get("trades", []) if isinstance(ledger, dict) else (ledger or [])
    if not isinstance(trades, list):
        trades = []
    by_analyst: dict[str, list[tuple[dict[str, Any], float]]] = defaultdict(list)
    rejected = 0
    seen_ids: set[str] = set()
    for record in trades:
        if not isinstance(record, dict):
            rejected += 1
            continue
        trade_id = str(record.get("trade_id", "")).strip()
        if not trade_id or trade_id in seen_ids:
            rejected += 1
            continue
        seen_ids.add(trade_id)
        valid, _, r_value = validate_verified_trade(record)
        if not valid or r_value is None:
            rejected += 1
            continue
        by_analyst[str(record["analyst_id"]).strip().casefold()].append((record, r_value))

    # Only analysts who published an explicit, named, registered view on the same symbol qualify.
    matched: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for candidate in analysis_candidates:
        if candidate.get("direction") not in {"bullish", "bearish"}:
            continue
        if not candidate.get("expert_eligible") or not candidate.get("named_author"):
            continue
        author = str(candidate["named_author"]).strip().casefold()
        if author not in by_analyst:
            continue
        for symbol in candidate.get("assets", []):
            matched[str(symbol)][author].add(str(candidate["direction"]))

    output: dict[str, dict[str, Any]] = {}
    for symbol, authors in matched.items():
        eligible_records = [
            (record, r_value)
            for author in authors
            for record, r_value in by_analyst[author]
            if str(record.get("symbol", "")).upper() == symbol.upper()
        ]
        metrics = calculate_performance([r for _, r in eligible_records], minimum_sample)
        authors_with_symbol = {
            str(record.get("analyst_id", "")).casefold()
            for record, _ in eligible_records
        }
        output[symbol] = {
            "verified_analyst_publishers": len(authors_with_symbol),
            "verified_trade_sample_size": metrics["sample_size"],
            "verified_expectancy_r": metrics["expectancy_r"],
            "verified_profit_factor": metrics["profit_factor"],
            "performance_verification_status": (
                "independently_verified" if metrics["ranking_eligible"] else "insufficient_verified_history"
            ),
            "verified_performance_metrics": metrics,
            "ledger_rejected_records": rejected,
            "ledger_method": "closed_trade_records_matched_to_named_registered_forecasters; external evidence must be independently reviewed",
        }
    return output
