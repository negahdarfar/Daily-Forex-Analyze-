"""Auditable FX-only research shortlist.

This ranks up to ten of the 28 configured FX pairs using only evidence present
in the current run. Missing macro/calendar evidence stays missing; this is not
an entry signal, probability, or substitute for broker execution checks.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import tanh
from typing import Any

from src.analysis.consensus import build_consensus


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
    policy_rates: dict[str, Any] | None = None,
    opportunity_candidates: list[dict[str, Any]] | None = None,
    currency_strength: dict[str, Any] | None = None,
    *,
    policy: dict[str, Any] | None = None,
    max_age_hours: float = 36.0,
) -> dict[str, Any]:
    """Create a provisional top-10 FX shortlist with explicit evidence coverage."""
    intelligence = market_intelligence or {}
    policy = policy or {}
    directional_evidence = directional_evidence or {}
    economic_calendar = economic_calendar or {}
    policy_rates = policy_rates or {}
    rate_rows = policy_rates.get("rates", {})
    candidate_by_symbol = {
        candidate.get("symbol"): candidate
        for candidate in (opportunity_candidates or [])
        if candidate.get("symbol")
    }
    max_pairs = max(1, min(10, int(policy.get("max_pairs", 10))))
    configured_weights = policy.get("weights", {
        "technical": 20, "mtf_confluence": 15, "fundamental": 20, "cot_positioning": 15,
        "news": 10, "expert_consensus": 10, "data_freshness": 5, "calendar_risk": 5,
    })
    weights = {
        key: float(value) for key, value in configured_weights.items()
        if key in {"technical", "mtf_confluence", "fundamental", "cot_positioning", "news", "expert_consensus", "data_freshness", "calendar_risk", "currency_strength", "market_structure"}
        and isinstance(value, (int, float)) and float(value) > 0
    }
    total_weight = sum(weights.values())
    currency_rows = {
        row.get("currency"): row
        for row in intelligence.get("currency_strength", [])
        if row.get("currency")
    }
    strength_rows = (currency_strength or {}).get("currencies", {})
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
        fundamental_score = None
        fundamental_status = "policy_rate_data_missing_or_stale"
        base_rate = rate_rows.get(base, {})
        quote_rate = rate_rows.get(quote, {})
        if (
            base_rate.get("status") == "available"
            and quote_rate.get("status") == "available"
            and isinstance(base_rate.get("policy_rate_pct"), (int, float))
            and isinstance(quote_rate.get("policy_rate_pct"), (int, float))
            and isinstance(base_rate.get("change_90d_pp"), (int, float))
            and isinstance(quote_rate.get("change_90d_pp"), (int, float))
        ):
            carry_diff = float(base_rate["policy_rate_pct"]) - float(quote_rate["policy_rate_pct"])
            policy_impulse_diff = float(base_rate["change_90d_pp"]) - float(quote_rate["change_90d_pp"])
            raw_fundamental = 0.65 * tanh(carry_diff / 2.0) + 0.35 * tanh(policy_impulse_diff / 0.5)
            direction_sign = 1.0 if direction == "bullish" else -1.0
            fundamental_score = _clamp(50.0 + 50.0 * direction_sign * raw_fundamental)
            fundamental_status = "policy_rate_carry_and_90d_change_proxy"
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
        candidate = candidate_by_symbol.get(symbol, {})
        timeframe_analyses = candidate.get("timeframes", {})
        required_timeframes = ("1d", "4h", "1h")
        mtf_rows = [
            timeframe_analyses.get(tf, {})
            for tf in required_timeframes
        ]
        mtf_score = None
        if all(
            row.get("status") == "ok"
            and row.get("direction") in {"bullish", "bearish"}
            and isinstance(row.get("score"), (int, float))
            for row in mtf_rows
        ):
            alignment_pct = 100.0 * sum(
                1 for row in mtf_rows if row.get("direction") == direction
            ) / len(required_timeframes)
            average_strength = sum(float(row["score"]) for row in mtf_rows) / len(required_timeframes)
            mtf_score = _clamp(0.60 * alignment_pct + 0.40 * average_strength)
        daily_freshness = _clamp(100.0 * (1.0 - float(age) / max(max_age_hours, 1.0)))
        quote_age_minutes = candidate.get("quote_age_minutes")
        max_quote_minutes = float(policy.get("max_intraday_quote_age_minutes", 180))
        if isinstance(quote_age_minutes, (int, float)) and 0 <= float(quote_age_minutes) <= max_quote_minutes:
            hourly_freshness = _clamp(100.0 * (1.0 - float(quote_age_minutes) / max(max_quote_minutes, 1.0)))
            freshness_score = _clamp(0.35 * daily_freshness + 0.65 * hourly_freshness)
        else:
            freshness_score = daily_freshness
        base_strength = strength_rows.get(base, {})
        quote_strength = strength_rows.get(quote, {})
        base_relative = base_strength.get("relative_score")
        quote_relative = quote_strength.get("relative_score")
        pair_strength_score = None
        if (base_strength.get("status") == "available"
                and quote_strength.get("status") == "available"
                and isinstance(base_relative, (int, float))
                and isinstance(quote_relative, (int, float))):
            relative_diff = float(base_relative) - float(quote_relative)
            sign = 1.0 if direction == "bullish" else -1.0
            pair_strength_score = _clamp(50.0 + sign * relative_diff / 2.0)
        structure = candidate.get("market_structure", {})
        structure_score = None
        recent_structure = []
        if structure.get("status") == "available":
            now_utc = datetime.now(timezone.utc)
            for event in structure.get("events", []):
                stamp_text = event.get("confirmed_at") or event.get("at")
                try:
                    stamp = datetime.fromisoformat(str(stamp_text).replace("Z", "+00:00"))
                    if stamp.tzinfo is None:
                        stamp = stamp.replace(tzinfo=timezone.utc)
                    age_hours_event = (now_utc - stamp.astimezone(timezone.utc)).total_seconds() / 3600
                    if 0 <= age_hours_event <= float(policy.get("structure_event_max_age_hours", 24)):
                        event_type = str(event.get("type", ""))
                        event_direction = event.get("direction")
                        if event_type.lower().startswith("bullish"):
                            event_direction = "bullish"
                        elif event_type.lower().startswith("bearish"):
                            event_direction = "bearish"
                        if event_direction in {"bullish", "bearish"}:
                            recent_structure.append((event_type, event_direction))
                except (TypeError, ValueError):
                    continue
        aligned_bos = any(kind in {"BOS", "CHoCH"} and side == direction for kind, side in recent_structure)
        opposed_bos = any(kind in {"BOS", "CHoCH"} and side != direction for kind, side in recent_structure)
        aligned_fvg = any("FVG" in kind and side == direction for kind, side in recent_structure)
        if aligned_bos and aligned_fvg:
            structure_score = 90.0
        elif aligned_bos:
            structure_score = 75.0
        elif aligned_fvg:
            structure_score = 60.0
        elif opposed_bos:
            structure_score = 20.0
        components: dict[str, float | None] = {
            "technical": _clamp(float(analysis.get("score", 0.0))),
            "mtf_confluence": mtf_score,
            "fundamental": fundamental_score,
            "cot_positioning": _pair_directional_spread(
                currency_rows, base, quote, "cot_score", direction
            ),
            "news": _pair_directional_spread(
                currency_rows, base, quote, "news_score", direction
            ),
            "expert_consensus": None,
            "data_freshness": freshness_score,
            "calendar_risk": calendar_score,
            "currency_strength": pair_strength_score,
            "market_structure": structure_score,
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

        consensus = build_consensus(
            {
                "technical": {"score": components["technical"], "verified": True, "fresh": True,
                              "source": "current-run technical analysis"},
                "macro": {"score": fundamental_score, "verified": fundamental_score is not None,
                          "fresh": policy_rates.get("status") == "available",
                          "source": policy_rates.get("source")},
                "currency_strength": {"score": pair_strength_score, "verified": pair_strength_score is not None,
                                      "fresh": True, "source": "current-run relative FX closes"},
            },
            weights={"technical": 1.0, "macro": 1.0, "currency_strength": 1.0},
            minimum_coverage_pct=float(policy.get("minimum_consensus_coverage_pct", 50.0)),
        )
        consensus["pair_direction"] = direction
        consensus["alignment_status"] = (
            "strong_alignment" if isinstance(consensus.get("score"), (int, float)) and consensus["score"] > 55
            else "opposed_evidence" if isinstance(consensus.get("score"), (int, float)) and consensus["score"] < 45
            else "mixed_or_neutral_evidence" if isinstance(consensus.get("score"), (int, float))
            else "insufficient_evidence"
        )
        consensus["direction"] = direction
        consensus["score_type"] = "pair_aligned_evidence_index_not_probability"
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
        if fundamental_score is None:
            missing.append("paired_policy_rate_data_missing_or_stale")
        else:
            missing.append("inflation_growth_labor_and_market_consensus_surprise_not_integrated")
        if mtf_score is None:
            missing.append("completed_1d_4h_1h_multitimeframe_confluence_missing")
        if components["cot_positioning"] is None:
            missing.append("paired_currency_cot_positioning")
        if components["news"] is None:
            missing.append("directional_currency_news")
        if components["expert_consensus"] is None:
            missing.append("two_or_more_independent_named_forex_analysts")
        if pair_strength_score is None:
            missing.append("relative_currency_strength_pair_coverage_missing")
        if structure_score is None:
            missing.append("recent_confirmed_market_structure_event_missing")
        if consensus.get("status") != "available":
            missing.append("verified_consensus_coverage_below_threshold")
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
            "consensus": consensus,
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
            "fundamental_status": fundamental_status,
            "calendar_status": calendar_status,
            "execution_status": "not_trade_qualified",
        })

    ranked.sort(key=lambda row: (
        row["score"],
        row.get("consensus", {}).get("coverage_pct", 0.0),
        row.get("consensus", {}).get("score") if isinstance(row.get("consensus", {}).get("score"), (int, float)) else -1.0,
        row["score_coverage_pct"],
        -row["data_age_hours"],
    ), reverse=True)
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
            "fundamental_integrated": policy_rates.get("status") == "available",
            "fundamental_scope": "BIS policy-rate carry and 90-day change proxy only",
            "policy_rate_source_status": policy_rates.get("status", "not_connected"),
            "economic_calendar_connected": economic_calendar.get("status") == "available",
            "mtf_confluence_integrated": any(
                isinstance(row.get("score_components", {}).get("mtf_confluence"), (int, float))
                for row in selected
            ),
            "technical_multitimeframe_entry_validation": False,
            "relative_currency_strength_integrated": bool(currency_strength and currency_strength.get("status") == "available"),
            "recent_market_structure_integrated": any(isinstance(row.get("score_components", {}).get("market_structure"), (int, float)) for row in selected),
            "evidence_consensus_integrated": True,
            "expert_consensus_threshold": int(policy.get("minimum_independent_expert_publishers", 2)),
            "us_calendar_status": economic_calendar.get("status", "not_connected"),
            "us_calendar_scope": economic_calendar.get("coverage", "not_connected"),
            "us_calendar_updated_at": economic_calendar.get("updated_at"),
            "non_us_calendar_covered": False,
        },
        "limitations": [
            "The fundamental component is only a BIS policy-rate carry and 90-day change proxy; inflation, growth, labor and market-consensus surprises are not integrated.",
            "The connected free calendar covers US high-impact releases only; the other seven currency legs remain unverified.",
            "Expert claims are unverified and count only when at least two independent specialist publishers provide named authors.",
            "A Yahoo Finance indicative quote is not an executable broker price; spread, commission, slippage and venue liquidity remain separate gates.",
            "The score is a relative research ranking, not a win probability or investment recommendation.",
        ],
    }
