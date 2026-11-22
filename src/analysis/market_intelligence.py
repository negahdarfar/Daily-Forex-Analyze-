"""Cross-domain FX intelligence built only from evidence actually collected.

No NLP/API claims are fabricated: news sentiment is deliberately conservative,
COT is used only when a 26+ week z-score exists, and missing domains are
renormalized out of the composite rather than treated as neutral evidence.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

CURRENCY_NAMES = {
    "USD": ("usd", "us dollar", "united states", "u.s."),
    "EUR": ("eur", "euro", "eurozone", "euro area"),
    "GBP": ("gbp", "pound", "sterling", "united kingdom", "uk economy"),
    "JPY": ("jpy", "yen", "japan", "boj", "bank of japan"),
    "CHF": ("chf", "swiss franc", "switzerland", "snb"),
    "CAD": ("cad", "canadian dollar", "canada", "bank of canada"),
    "AUD": ("aud", "australian dollar", "australia", "rba"),
    "NZD": ("nzd", "new zealand dollar", "new zealand", "rbnz"),
}
COT_CURRENCY_TERMS = {
    "USD": ("us dollar", "u.s. dollar", "dollar index"),
    "EUR": ("euro fx", "euro"),
    "GBP": ("british pound", "pound sterling"),
    "JPY": ("japanese yen", "yen"),
    "CHF": ("swiss franc",),
    "CAD": ("canadian dollar",),
    "AUD": ("australian dollar",),
    "NZD": ("new zealand dollar",),
}
POSITIVE = ("hawkish", "rate hike", "raises rates", "stronger than expected", "beats forecast",
            "inflation accelerates", "growth accelerates", "bullish", "rises", "surges", "upgrade")
NEGATIVE = ("dovish", "rate cut", "cuts rates", "weaker than expected", "misses forecast",
            "inflation cools", "growth slows", "bearish", "falls", "slumps", "downgrade")


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _currency_mentions(text: str) -> set[str]:
    lowered = text.lower()
    found = set()
    for code, terms in CURRENCY_NAMES.items():
        if any(re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", lowered) for term in terms):
            found.add(code)
    return found


def _news_scores(news: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, int]]:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    now = datetime.now(timezone.utc)
    for item in news:
        if item.get("status") == "source_error":
            continue
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        mentions = _currency_mentions(text)
        if not mentions:
            continue
        pos = sum(1 for term in POSITIVE if term in text)
        neg = sum(1 for term in NEGATIVE if term in text)
        if pos == neg:
            continue
        age = item.get("age_hours")
        freshness = 1.0 if age is None else _clamp(1.0 - max(0.0, float(age)) / (24.0 * 7.0), 0.15, 1.0)
        # A feed headline is weak evidence; repeated currencies in one item count once.
        signal = _clamp((pos - neg) / max(2.0, pos + neg)) * freshness
        for code in mentions:
            totals[code] += signal
            counts[code] += 1
    return ({k: _clamp(v / max(1, counts[k])) for k, v in totals.items()}, dict(counts))


def _cot_scores(datasets: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    totals: dict[str, list[float]] = defaultdict(list)
    details: dict[str, dict[str, Any]] = {}
    for dataset in datasets:
        if dataset.get("source") != "CFTC" or dataset.get("status") != "available":
            continue
        for obs in dataset.get("observations", []):
            contract = str(obs.get("contract", "")).lower()
            zscore = obs.get("net_position_52w_zscore")
            weeks = int(obs.get("history_weeks") or 0)
            if zscore is None or weeks < 26:
                continue
            for code, terms in COT_CURRENCY_TERMS.items():
                if any(term in contract for term in terms):
                    value = math.tanh(float(zscore) / 2.0)
                    totals[code].append(value)
                    details[code] = {
                        "zscore": float(zscore), "weeks": weeks,
                        "report_date": obs.get("report_date"), "contract": obs.get("contract"),
                    }
                    break
    return ({k: sum(v) / len(v) for k, v in totals.items()}, details)


def build_market_intelligence(
    results: list[dict[str, Any]],
    news: list[dict[str, Any]],
    official_macro: list[dict[str, Any]],
    analysis_candidates: list[dict[str, Any]],
    source_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create auditable currency-strength and pair-confluence snapshot."""
    tech_total: dict[str, float] = defaultdict(float)
    tech_count: dict[str, int] = defaultdict(int)
    fresh_pairs = 0
    stale_pairs = 0
    for item in results:
        symbol = str(item.get("asset", ""))
        if len(symbol) != 6 or item.get("status") != "available":
            if len(symbol) == 6 and item.get("status") == "stale":
                stale_pairs += 1
            continue
        analysis = item.get("analysis", {})
        if analysis.get("status") != "ok" or analysis.get("direction") not in ("bullish", "bearish"):
            continue
        base, quote = symbol[:3], symbol[3:]
        if base not in CURRENCY_NAMES or quote not in CURRENCY_NAMES:
            continue
        signed = float(analysis.get("score", 0.0)) / 100.0
        if analysis["direction"] == "bearish":
            signed *= -1.0
        tech_total[base] += signed
        tech_total[quote] -= signed
        tech_count[base] += 1
        tech_count[quote] += 1
        fresh_pairs += 1

    technical = {code: _clamp(tech_total[code] / max(1, tech_count[code])) for code in CURRENCY_NAMES}
    news_score, news_count = _news_scores(news)
    cot_score, cot_details = _cot_scores(official_macro)

    currency_rows = []
    for code in CURRENCY_NAMES:
        parts = []
        if tech_count[code]:
            parts.append(("technical_relative_strength", technical[code], 0.60))
        if code in cot_score:
            parts.append(("cot_positioning", cot_score[code], 0.25))
        if news_count.get(code, 0):
            parts.append(("headline_directional_clues", news_score[code], 0.15))
        denom = sum(weight for _, _, weight in parts)
        composite = sum(value * weight for _, value, weight in parts) / denom if denom else None
        currency_rows.append({
            "currency": code,
            "score": round(composite * 100.0, 1) if composite is not None else None,
            "technical_score": round(technical[code] * 100.0, 1) if tech_count[code] else None,
            "technical_pair_samples": tech_count[code],
            "cot_score": round(cot_score[code] * 100.0, 1) if code in cot_score else None,
            "cot_evidence": cot_details.get(code),
            "news_score": round(news_score[code] * 100.0, 1) if code in news_count else None,
            "news_items": news_count.get(code, 0),
            "domains_used": [name for name, _, _ in parts],
            "status": "scored" if parts else "insufficient_evidence",
        })

    score_map = {row["currency"]: row["score"] for row in currency_rows}
    pair_rows = []
    for item in results:
        symbol = str(item.get("asset", ""))
        if len(symbol) != 6 or item.get("status") != "available":
            continue
        base, quote = symbol[:3], symbol[3:]
        if base not in score_map or quote not in score_map:
            continue
        bs, qs = score_map[base], score_map[quote]
        if bs is None or qs is None:
            continue
        spread = round(bs - qs, 1)
        analysis = item.get("analysis", {})
        tech_direction = analysis.get("direction", "unknown")
        ensemble_direction = "bullish" if spread >= 8 else "bearish" if spread <= -8 else "neutral"
        alignment = (
            "aligned" if ensemble_direction == tech_direction
            else "conflict" if ensemble_direction != "neutral" and tech_direction in ("bullish", "bearish")
            else "no_independent_confirmation"
        )
        pair_rows.append({
            "pair": symbol, "base_score": bs, "quote_score": qs,
            "strength_spread": spread, "ensemble_direction": ensemble_direction,
            "technical_direction": tech_direction, "confluence": alignment,
            "technical_score": analysis.get("score"),
            "market_timestamp": item.get("market_timestamp"),
        })
    pair_rows.sort(key=lambda row: abs(row["strength_spread"]), reverse=True)

    registry = source_registry or {}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "currency_strength": sorted(currency_rows, key=lambda row: row["score"] if row["score"] is not None else -999, reverse=True),
        "pair_confluence": pair_rows,
        "coverage": {
            "fresh_fx_pairs_with_direction": fresh_pairs,
            "stale_fx_pairs": stale_pairs,
            "news_items_received": len([n for n in news if n.get("status") != "source_error"]),
            "news_currency_mentions": sum(news_count.values()),
            "currencies_with_cot_zscore": len(cot_score),
            "macro_datasets_available": len([d for d in official_macro if d.get("status") == "available"]),
            "macro_datasets_total": len(official_macro),
            "analysis_claims_unverified": len(analysis_candidates),
            "registered_sources": registry.get("total", 0),
            "enabled_sources": registry.get("enabled", 0),
        },
        "methodology": {
            "weights": {"technical_relative_strength": 0.60, "cot_positioning": 0.25, "headline_directional_clues": 0.15},
            "dynamic_weighting": "Unavailable domains are excluded and remaining weights renormalized.",
            "limitations": "Daily timeframe only; news uses explicit keyword clues from public RSS metadata, not semantic verification. COT is included only with 26+ weeks. Macro releases are displayed as context, not assigned simplistic bullish/bearish labels. Composite is a research score, not probability or trade signal.",
        },
    }
