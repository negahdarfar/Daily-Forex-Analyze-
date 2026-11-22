"""Public RSS collector. Does not scrape social networks or private sources."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import requests



MARKET_TERMS = {
    "federal reserve", "fed ", "ecb", "bank of england", "boj",
    "central bank", "interest rate", "rate cut", "rate hike", "inflation",
    "cpi", "pce", "nonfarm", "payroll", "unemployment", "treasury yield",
    "bond yield", "us dollar", "dollar index", "forex", "currency",
    "exchange rate", "gold", "silver", "crude oil", "oil price", "opec",
    "bitcoin", "ethereum", "crypto", "cryptocurrency", "stock market",
    "equity market", "s&p 500", "nasdaq", "dow jones", "commodit",
    "gdp", "pmi", "recession", "trade war", "tariff", "investor",
    "market volatility", "market sell-off", "market rally", "financial market"
}


def classify_relevance(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    return "market_relevant" if any(term in text for term in MARKET_TERMS) else "general_business"


def _published(entry: Any) -> str | None:
    value = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if value:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
        except (TypeError, ValueError):
            return None
    return None


def collect_news(sources: list[dict], settings: dict | None = None) -> list[dict]:
    settings = settings or {}
    timeout = int(settings.get("timeout_seconds", 12))
    max_items = int(settings.get("max_items_per_source", 12))
    now = datetime.now(timezone.utc)
    collected, seen = [], set()

    for source in sources:
        if source.get("enabled", True) is False:
            continue
        url = source.get("url")
        if not url:
            continue
        try:
            response = requests.get(
                url, timeout=timeout,
                headers={"User-Agent": "DailyMarketAnalyze/1.0 (public RSS reader)"}
            )
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
            if parsed.bozo and not parsed.entries:
                raise ValueError("RSS/Atom parse failed")
            for entry in parsed.entries[:max_items]:
                link = getattr(entry, "link", "") or ""
                title = getattr(entry, "title", "") or ""
                identity = link or title
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                published_at = _published(entry)
                age_hours = None
                if published_at:
                    age_hours = round((now - datetime.fromisoformat(published_at)).total_seconds() / 3600, 1)
                collected.append({
                    "title": title.strip(), "url": link,
                    "author": getattr(entry, "author", None) or "not_provided",
                    "source": source.get("name", "Unknown RSS"),
                    "reliability": source.get("reliability", "unrated"),
                    "published_at": published_at or "unknown",
                    "collected_at": now.isoformat(), "age_hours": age_hours,
                    "status": "dated" if published_at else "publication_time_unavailable",
                    "relevance": classify_relevance(title, getattr(entry, "summary", "") or ""),
                    "summary": (getattr(entry, "summary", "") or "").replace("\\n", " ")[:500]
                })
        except Exception as exc:
            collected.append({
                "title": f"منبع خبری در دسترس نیست: {source.get('name', url)}",
                "url": url, "source": source.get("name", "Unknown RSS"),
                "reliability": source.get("reliability", "unrated"),
                "published_at": "unknown", "collected_at": now.isoformat(),
                "age_hours": None, "status": "source_error",
                "summary": f"{type(exc).__name__}: {exc}"
            })
    collected.sort(key=lambda item: item.get("published_at", ""), reverse=True)
    return collected
