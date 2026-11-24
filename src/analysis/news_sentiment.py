"""Transparent, conservative keyword sentiment baseline for financial headlines.

This is deliberately a heuristic, not an LLM claim or a causal market-impact model.
"""
from __future__ import annotations
import re
from collections import Counter

POSITIVE = {"beats", "surge", "rises", "growth", "hawkish", "upgrade", "record", "strong", "rebound", "inflow"}
NEGATIVE = {"misses", "falls", "drop", "slump", "recession", "dovish", "downgrade", "weak", "crisis", "outflow"}
NEGATION = {"not", "no", "never", "fails_to", "without"}


def score_headline(headline: str) -> dict:
    text = re.sub(r"[^a-z0-9_\s-]", " ", str(headline).lower())
    tokens = text.split()
    pos, neg = Counter(tokens), Counter(tokens)
    positive_hits = [w for w in tokens if w in POSITIVE]
    negative_hits = [w for w in tokens if w in NEGATIVE]
    # A nearby negator reverses the polarity of a matched term.
    for i, word in enumerate(tokens):
        if word in POSITIVE and any(t in NEGATION for t in tokens[max(0, i-2):i]):
            positive_hits.remove(word)
            negative_hits.append(word)
        elif word in NEGATIVE and any(t in NEGATION for t in tokens[max(0, i-2):i]):
            negative_hits.remove(word)
            positive_hits.append(word)
    raw = len(positive_hits) - len(negative_hits)
    total = len(positive_hits) + len(negative_hits)
    score = round(raw / total, 3) if total else None
    return {
        "score": score,
        "label": "positive" if score is not None and score > 0 else "negative" if score is not None and score < 0 else "neutral_or_unclassified",
        "positive_terms": positive_hits,
        "negative_terms": negative_hits,
        "matched_terms": total,
        "method": "small transparent keyword lexicon with local negation",
        "confidence": "low" if total <= 1 else "heuristic",
        "warning": "Headline polarity is not currency-specific impact; validate article context and deduplicate syndicated stories.",
    }


def deduplicate_headlines(items: list[dict]) -> list[dict]:
    seen, output = set(), []
    for item in items:
        title = re.sub(r"\W+", " ", str(item.get("title", "")).lower()).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        output.append(item)
    return output
