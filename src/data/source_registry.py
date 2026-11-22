"""Read-only audit helpers for the research-source registry."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_source_registry(path: Path) -> dict[str, Any]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    sources = registry.get("sources", [])
    ids = [item.get("id") for item in sources]
    if not sources or len(ids) != len(set(ids)) or any(not item.get("name") or not item.get("homepage") for item in sources):
        raise ValueError("Source registry must contain uniquely identified, named sources with homepages")
    if len(sources) != 100:
        raise ValueError(f"Expected exactly 100 registered sources, found {len(sources)}")
    for item in sources:
        score = item.get("authority_score")
        if not isinstance(score, (int, float)) or not 0 <= score <= 100:
            raise ValueError(f"Invalid authority_score for {item.get('name')}")
        if item.get("enabled") and not item.get("feed_url") and item.get("access_method") != "active_existing_rss":
            # Existing RSS sources without a feed URL must be explicitly identified as validated legacy connectors.
            if item.get("status") != "active_existing_rss":
                raise ValueError(f"Enabled source has no validated feed URL: {item.get('name')}")
    return registry


def summarize_source_registry(registry: dict[str, Any]) -> dict[str, Any]:
    sources = registry.get("sources", [])
    return {
        "total": len(sources),
        "enabled": sum(bool(item.get("enabled")) for item in sources),
        "permission_required": sum(item.get("status") == "permission_required" for item in sources),
        "manual_only": sum(item.get("access_method") in {"manual_link_only", "official_api_or_manual_only", "manual_link_or_authorized_api"} for item in sources),
        "categories": {
            category: sum(item.get("category") == category for item in sources)
            for category in sorted({item.get("category", "uncategorized") for item in sources})
        },
        "authority_tiers": {
            tier: sum(item.get("reliability_tier") == tier for item in sources)
            for tier in sorted({item.get("reliability_tier", "unassessed") for item in sources})
        },
        "ordering_policy": registry.get("ordering_policy", []),
    }



def annotate_analysis_candidates(candidates: list[dict[str, Any]], registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach a transparent prior authority weight to explicit source claims."""
    sources = registry.get("sources", [])
    output = []
    for candidate in candidates:
        label = str(candidate.get("source", "")).casefold().strip()
        match = next((s for s in sources if s.get("name", "").casefold() == label), None)
        if match is None:
            match = next((s for s in sources if s.get("name", "").casefold() in label or label in s.get("name", "").casefold()), None)
        enriched = dict(candidate)
        enriched["source_authority_score"] = match.get("authority_score", 0) if match else 0
        enriched["source_reliability_tier"] = match.get("reliability_tier", "unmatched") if match else "unmatched"
        enriched["source_registry_match"] = match.get("name") if match else None
        output.append(enriched)
    return output


def summarize_directional_evidence(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Summarize explicit bullish/bearish claims; cap each publisher to one vote per asset."""
    grouped: dict[str, dict[str, dict[str, float]]] = {}
    for item in candidates:
        direction = item.get("direction")
        if direction not in {"bullish", "bearish"}:
            continue
        score = float(item.get("source_authority_score", 0) or 0)
        if score <= 0:
            continue
        publisher = str(item.get("source_registry_match") or item.get("source") or "unknown")
        for asset in item.get("assets", []):
            grouped.setdefault(asset, {}).setdefault(direction, {})
            grouped[asset][direction][publisher] = max(grouped[asset][direction].get(publisher, 0.0), score)
    result = {}
    for asset, sides in grouped.items():
        bull = sum(sides.get("bullish", {}).values())
        bear = sum(sides.get("bearish", {}).values())
        total = bull + bear
        result[asset] = {
            "bullish_weight": round(bull, 1),
            "bearish_weight": round(bear, 1),
            "net_bias": round((bull - bear) / total, 3) if total else 0.0,
            "bullish_publishers": len(sides.get("bullish", {})),
            "bearish_publishers": len(sides.get("bearish", {})),
            "status": "directional_evidence_present" if total else "no_directional_evidence",
            "method": "explicit_direction_only; publisher capped once per asset and direction; authority prior, not calibrated probability",
        }
    return result
