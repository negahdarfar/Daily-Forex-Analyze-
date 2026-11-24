"""Evidence-aware directional consensus; missing inputs never become neutral votes."""
from __future__ import annotations
from typing import Any

DOMAINS = ("technical", "macro", "news", "positioning", "expert", "currency_strength")


def build_consensus(evidence: dict[str, dict[str, Any]], weights: dict[str, float] | None = None,
                    minimum_coverage_pct: float = 50.0) -> dict:
    weights = weights or {name: 1.0 for name in DOMAINS}
    valid_weights = {k: float(v) for k, v in weights.items() if k in DOMAINS and isinstance(v, (int, float)) and v > 0}
    total_weight = sum(valid_weights.values())
    if total_weight <= 0:
        return {"status": "unavailable", "direction": "neutral", "score": None, "coverage_pct": 0.0, "domains": {}}
    used, detail = {}, {}
    for domain, weight in valid_weights.items():
        item = evidence.get(domain) or {}
        score = item.get("score")
        direction = item.get("direction")
        verified = item.get("verified", False)
        fresh = item.get("fresh", False)
        if not verified or not fresh or not isinstance(score, (int, float)) or not 0 <= float(score) <= 100:
            detail[domain] = {"status": "excluded_missing_unverified_or_stale"}
            continue
        used[domain] = (float(score), weight)
        detail[domain] = {"status": "included", "score": round(float(score), 2), "weight": weight,
                          "direction": direction, "source": item.get("source"), "as_of": item.get("as_of")}
    covered = sum(weight for _, weight in used.values())
    coverage = 100.0 * covered / total_weight
    if not used or coverage < minimum_coverage_pct:
        return {"status": "insufficient_evidence", "direction": "neutral", "score": None,
                "coverage_pct": round(coverage, 1), "domains": detail,
                "warning": "Insufficient verified, fresh evidence; no directional consensus emitted."}
    score = sum(value * weight for value, weight in used.values()) / covered
    direction = "bullish" if score > 55 else "bearish" if score < 45 else "neutral"
    bullish = sum(weight for name, (value, weight) in used.items() if value > 55)
    bearish = sum(weight for name, (value, weight) in used.items() if value < 45)
    conflict = min(bullish, bearish) / max(bullish + bearish, 1e-9)
    return {"status": "available", "direction": direction, "score": round(score, 2),
            "coverage_pct": round(coverage, 1), "conflict_ratio": round(conflict, 3),
            "domains": detail,
            "score_type": "weighted_evidence_index_not_probability",
            "warning": "Consensus is a research filter, not a forecast probability or trade instruction."}
