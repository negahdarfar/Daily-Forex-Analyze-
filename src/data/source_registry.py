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
