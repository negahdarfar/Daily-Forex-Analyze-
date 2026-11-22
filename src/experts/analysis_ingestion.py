"""Evidence-preserving extraction of structured analysis clues from permitted feed metadata."""
from __future__ import annotations

import re
from typing import Any


ANALYSIS_TERMS = (
    "analysis", "forecast", "outlook", "price target", "technical view",
    "support", "resistance", "bullish", "bearish", "elliott", "wave count",
    "trading setup", "market view", "breakout", "downside", "upside",
)
DIRECTION_TERMS = {
    "bullish": ("bullish", "bull", "upside", "higher", "rally", "long", "buy"),
    "bearish": ("bearish", "bear", "downside", "lower", "selloff", "short", "sell"),
}
METHOD_TERMS = {
    "elliott_wave": ("elliott wave", "wave count", "impulse wave", "corrective wave"),
    "smc_ict": ("smart money", "ict", "order block", "fair value gap", "liquidity sweep", "choch", "bos"),
    "price_action": ("price action", "breakout", "candlestick", "support", "resistance"),
    "technical_indicators": ("rsi", "macd", "moving average", "ichimoku", "fibonacci"),
    "fundamental_macro": ("central bank", "interest rate", "inflation", "gdp", "payroll", "monetary policy"),
}
TIMEFRAME_PATTERN = re.compile(r"\b(\d+\s*(?:m|min|h|hr|d|day|w|wk|mo)|daily|weekly|monthly|intraday)\b", re.I)
LEVEL_PATTERNS = {
    "target": re.compile(r"\b(?:target|price target|take[- ]profit|tp)\s*(?:at|:|=)?\s*(\d+(?:\.\d+)?)", re.I),
    "entry": re.compile(r"\b(?:entry|enter|buy above|sell below)\s*(?:at|:|=)?\s*(\d+(?:\.\d+)?)", re.I),
    "stop_loss": re.compile(r"\b(?:stop[- ]loss|stop|sl)\s*(?:at|:|=)?\s*(\d+(?:\.\d+)?)", re.I),
    "invalidation": re.compile(r"\b(?:invalidation|invalidated below|invalidated above)\s*(?:at|:|=)?\s*(\d+(?:\.\d+)?)", re.I),
}


def _normalise_symbol(value: str) -> str:
    return re.sub(r"[^A-Z]", "", value.upper())


def _find_assets(text: str, known_assets: list[str]) -> list[str]:
    normalised = {_normalise_symbol(item): item for item in known_assets}
    found = []
    for match in re.findall(r"\b[A-Z]{3,6}/?[A-Z]{3,6}\b", text.upper()):
        key = _normalise_symbol(match)
        if key in normalised and normalised[key] not in found:
            found.append(normalised[key])
    for key, original in normalised.items():
        if len(key) >= 6 and re.search(rf"(?<![A-Z0-9]){re.escape(key)}(?![A-Z0-9])", text.upper()):
            if original not in found:
                found.append(original)
    return found


def extract_analysis_candidates(items: list[dict[str, Any]], known_assets: list[str]) -> list[dict[str, Any]]:
    """Extract only explicit clues; never infer missing levels, timeframe or direction."""
    output = []
    seen = set()
    for item in items:
        if item.get("status") == "source_error":
            continue
        title = item.get("title", "") or ""
        summary = item.get("summary", "") or ""
        text = f"{title} {summary}"
        lowered = text.lower()
        assets = _find_assets(text, known_assets)
        methods = [name for name, terms in METHOD_TERMS.items() if any(term in lowered for term in terms)]
        has_analysis_language = any(term in lowered for term in ANALYSIS_TERMS)
        if not (has_analysis_language and (assets or methods)):
            continue
        identity = item.get("url") or f"{item.get('source')}|{title}"
        if identity in seen:
            continue
        seen.add(identity)
        directions = [direction for direction, terms in DIRECTION_TERMS.items() if any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in terms)]
        direction = directions[0] if len(directions) == 1 else ("conflicting" if len(directions) > 1 else "not_stated")
        timeframes = list(dict.fromkeys(match.group(1).lower().replace(" ", "") for match in TIMEFRAME_PATTERN.finditer(text)))
        levels = {}
        for field, pattern in LEVEL_PATTERNS.items():
            match = pattern.search(text)
            if match:
                try:
                    levels[field] = float(match.group(1))
                except ValueError:
                    pass
        output.append({
            "title": title,
            "source": item.get("source", "unknown"),
            "author": item.get("author") or "not_provided",
            "url": item.get("url", ""),
            "published_at": item.get("published_at", "unknown"),
            "collected_at": item.get("collected_at", "unknown"),
            "assets": assets,
            "direction": direction,
            "timeframes": timeframes,
            "methodologies": methods,
            "levels": levels,
            "evidence_excerpt": summary[:500],
            "verification_status": "unverified_source_claim",
            "extraction_status": "explicit_fields_only",
        })
    return output
