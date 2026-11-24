"""Auditable FX-only research shortlist.

This ranks up to ten of the 28 configured FX pairs using only evidence present
in the current run. Missing macro/calendar evidence stays missing; this is not
an entry signal, probability, or substitute for broker execution checks.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


CURRENCY_CODES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _pair_directional_spread(
    currency_rows: dict[str, dict[str, Any]],
    base: str,
    quote: str,
    field: str,
    direction: str,
) -> float | None:
    left = currency_rows.get(base, {}).get(field)
    right = currency_rows.get(quote, {}).get(field)
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return None
    sign = 1.0 if direction == "bullish" else -1.0
    # Currency evidence is normalized to [-100, 100]; map pair-relative
    # difference to [0, 100] without treating unavailable evidence as neutral.
    return _clamp(50.0 + sign * (float(left) - float(right)) / 4.0)


def rank_fx_pairs(
    results: list[dict[str, Any]],
    market_intelligence: dict[str, Any] | None = None,
    directional_evidence: dict[str, dict[str, Any]] | None = None,
    economic_calendar: dict[str, Any] | None = None,
    *,
    policy: dict[str, Any] | None = None,
    max_age_hours: float = 36.0,
) -> dict[str, Any]:
    """Create a provisional top-10 FX shortlist with explicit evidence coverage."""
    intelligence = market_intelligence or {}
    policy = policy or {}
    directional_evidence = directional_evidence or {}
    economic_calendar = economic_calendar or {}
    max_pairs = max(1, min(10, int(policy.get("max_pairs", 10))))
    configured_weights = policy.get("weights", {
        "technical": 30, "fundamental": 20, "cot_positioning": 15, "news": 10,
        "expert_consensus": 10, "data_freshness": 10, "calendar_risk": 5,
    })
    weights = {
        key: float(value) for key, value in configured_weights.items()
        if key in {"technical", "fundamental", "cot_positioning", "news", "expert_consensus", "data_freshness", "calendar_risk"}
        and isinstance(value, (int, float)) and float(value) > 0
    }
    total_weight = sum(weights.values())
    currency_rows = {
        row.get("currency"): row
        for row in intelligence.get("currency_strength", [])
        if row.get("currency")
    }
    ranked = []
    excluded = {"unavailable": 0, "stale": 0, "invalid": 0, "neutral": 0}

    for item in results:
        symbol = str(item.get("asset", ""))
        if len(symbol) != 6 or not symbol.isalpha() or symbol[:3] not in CURRENCY_CODES or symbol[3:] not in CURRENCY_CODES:
            continue
        if item.get("status") == "stale":
            excluded["stale"] += 1
            continue
        if item.get("status") != "available":
            excluded["unavailable"] += 1
            continue
        analysis = item.get("analysis") or {}
        if analysis.get("status") != "ok":
            excluded["invalid"] += 1
            continue
        direction = analysis.get("direction")
        if direction not in {"bullish", "bearish"}:
            excluded["neutral"] += 1
            continue

        age = item.get("age_hours")
        if not isinstance(age, (int, float)) or float(age) < 0 or float(age) > max_age_hours:
            excluded["stale"] += 1
            continue

        base, quote = symbol[:3], symbol[3:]
        calendar_score = None
        calendar_status = "non_us_currency_calendar_not_covered"
        if "USD" in {base, quote}:
            if economic_calendar.get("status") == "available":
                now = datetime.now(timezone.utc)
                before = float(policy.get("event_blackout_minutes_before", 30))
                after = float(policy.get("event_blackout_minutes_after", 30))
                near_events = []
                for event in economic_calendar.get("events", []):
                    try:
                        event_time = datetime.fromisoformat(
                            str(event.get("scheduled_at_utc", "")).replace("Z", "+00:00")
                        )
                        if event_time.tzinfo is None:
                            event_time = event_time.replace(tzinfo=timezone.utc)
                        minutes = (event_time.astimezone(timezone.utc) - now).total_seconds() / 60.0
                        if -after <= minutes <= before:
                            near_events.append(event)
                    except (TypeError, ValueError):
                        continue
                calendar_score = 0.0 if near_events else 100.0
                calendar_status = (
                    "high_impact_us_event_blackout" if near_events
                    else "us_calendar_no_near_high_impact_event_partial_coverage"
                )
            elif economic_calendar.get("status") == "stale":
                calendar_status = "stale_us_calendar_unknown"
            else:
                calendar_status = "us_calendar_unavailable_unknown"
        components: dict[str, float | None] = {
            "technical": _clamp(float(analysis.get("score", 0.0))),
            "fundamental": None,
            "cot_positioning": _pair_directional_spread(
                currency_rows, base, quote, "cot_score", direction
            ),
            "news": _pair_directional_spread(
                currency_rows, base, quote, "news_score", direction
            ),
            "expert_consensus": None,
            "data_freshness": _clamp(100.0 * (1.0 - float(age) / max(max_age_hours, 1.0))),
            "calendar_risk": calendar_score,
        }
        expert = directional_evidence.get(symbol, {})
        publishers = int(expert.get("bullish_publishers", 0) or 0) + int(expert.get("bearish_publishers", 0) or 0)
        # A single unverified publisher is shown in the report but is not treated
        # as a consensus component.
        if publishers >= int(policy.get("minimum_independent_expert_publishers", 2)):
            net_bias = expert.get("net_bias")
            if isinstance(net_bias, (int, float)):
                sign = 1.0 if direction == "bullish" else -1.0
                components["expert_consensus"] = _clamp(50.0 + 50.0 * sign * float(net_bias))

        available = {
            key: value for key, value in components.items()
            if key in weights and isinstance(value, (int, float))
        }
        covered_weight = sum(weights[key] for key in available)
        if not available or covered_weight <= 0:
            continue
        score = sum(float(available[key]) * weights[key] for key in available) / covered_weight
        coverage_pct = 100.0 * covered_weight / total_weight if total_weight else 0.0

        missing = []
        # These domains are intentionally not inferred from proxy data.
        missing.append("fundamental_rate_path_and_comparable_macro_surprise")
        if components["cot_positioning"] is None:
            missing.append("paired_currency_cot_positioning")
        if components["news"] is None:
            missing.append("directional_currency_news")
        if components["expert_consensus"] is None:
            missing.append("two_or_more_independent_forex_analysis_publishers")
        if calendar_score is None:
            missing.append(
                "fresh_us_economic_calendar_required" if "USD" in {base, quote}
                else "calendar_for_non_us_currency_required"
            )
        if calendar_status == "high_impact_us_event_blackout":
            missing.append("high_impact_us_event_blackout_window")

        ranked.append({
            "symbol": symbol,
            "direction": direction,
            "score": round(score, 2),
            "score_type": "provisional_evidence_weighted_shortlist_not_probability",
            "score_coverage_pct": round(coverage_pct, 1),
            "score_components": components,
            "available_components": sorted(available),
            "missing_evidence": missing,
            "expert_publishers": publishers,
            "market_timestamp": item.get("market_timestamp"),
            "data_age_hours": round(float(age), 2),
            "price": analysis.get("close"),
            "rsi": analysis.get("rsi14"),
            "adx": analysis.get("adx"),
            "atr_pct": analysis.get("atr_pct"),
            "confluence": (
                "technical_and_nonprice_evidence_aligned"
                if any(
                    isinstance(components[key], (int, float))
                    and components[key] >= 60.0
                    for key in ("cot_positioning", "news", "expert_consensus")
                )
                else "technical_only_or_insufficient_confirmation"
            ),
            "fundamental_status": "not_integrated",
            "calendar_status": calendar_status,
            "execution_status": "not_trade_qualified",
        })

    ranked.sort(key=lambda row: (row["score"], row["score_coverage_pct"], -row["data_age_hours"]), reverse=True)
    selected = [{**row, "rank": rank} for rank, row in enumerate(ranked[:max_pairs], 1)]
    return {
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ranking_type": "FX research shortlist; not an entry signal",
        "requested_max_pairs": max_pairs,
        "ranked_count": len(selected),
        "eligible_directional_pairs": len(ranked),
        "opportunities": selected,
        "excluded": excluded,
        "coverage": {
            "fundamental_integrated": False,
            "economic_calendar_connected": economic_calendar.get("status") == "available",
            "technical_multitimeframe_entry_validation": False,
            "expert_consensus_threshold": int(policy.get("minimum_independent_expert_publishers", 2)),
            "us_calendar_status": economic_calendar.get("status", "not_connected"),
            "us_calendar_scope": economic_calendar.get("coverage", "not_connected"),
            "us_calendar_updated_at": economic_calendar.get("updated_at"),
            "non_us_calendar_covered": False,
        },
        "limitations": [
            "Fundamental rate-path and synchronized macro-surprise scoring are not yet integrated into this shortlist.",
            "The connected free calendar covers US high-impact releases only; the other seven currency legs remain unverified.",
            "Expert claims are unverified and count only when at least two independent forex-analysis publishers are present.",
            "A Yahoo Finance indicative quote is not an executable broker price; spread, commission, slippage and venue liquidity remain separate gates.",
            "The score is a relative research ranking, not a win probability or investment recommendation.",
        ],
    }
