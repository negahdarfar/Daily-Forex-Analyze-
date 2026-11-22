from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.data.market_data import fetch_asset_history
from src.data.news import collect_news
from src.data.official_data import fetch_ecb_reference_rates, fetch_world_bank_inflation, fetch_bls_macro, fetch_cftc_cot
from src.data.source_registry import load_source_registry, summarize_source_registry, annotate_analysis_candidates, summarize_directional_evidence, merge_active_rss_sources
from src.experts.analysis_ingestion import extract_analysis_candidates
from src.reporting.markdown import render_report
from src.technical.indicators import analyze

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    assets = load_json(ROOT / "config" / "assets.json")
    settings = load_json(ROOT / "config" / "settings.json")
    results = []
    enabled = []
    for category in ("forex", "commodities", "crypto"):
        enabled.extend(a for a in assets.get(category, []) if a.get("enabled"))

    for asset in enabled:
        fetched = fetch_asset_history(
            asset,
            period=settings.get("history_period", "6mo"),
            interval=settings.get("history_interval", "1d")
        )
        item = {
            "asset": asset["symbol"],
            "provider": fetched.get("provider", "—"),
            "status": fetched.get("status", "unknown"),
            "market_timestamp": fetched.get("market_timestamp", "—"),
            "collected_at": fetched.get("collected_at", "—"),
            "sources_checked": ", ".join(fetched.get("sources_checked", [])) or "—",
            "source_selection": fetched.get("source_selection", "single_source"),
            "reason": fetched.get("reason", "—")
        }
        if fetched.get("status") == "available":
            item["analysis"] = analyze(fetched["history"], settings)
            stamp = fetched.get("market_timestamp")
            if stamp:
                market_time = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - market_time).total_seconds() / 3600
                item["age_hours"] = round(max(0.0, age_hours), 1)
                max_age = float(settings.get("max_quote_age_hours", 36))
                if age_hours > max_age:
                    item["status"] = "stale"
                    item["reason"] = f"آخرین کندل {item['age_hours']} ساعت قبل است؛ از رتبه‌بندی فرصت‌ها حذف شد."
        else:
            item["analysis"] = {"status": "unavailable"}
        results.append(item)
        print(f"{asset['symbol']}: {item['status']}")

    for asset in assets.get("iran_local", []):
        if not asset.get("enabled"):
            results.append({
                "asset": asset["symbol"], "provider": "not_configured",
                "status": "unavailable", "market_timestamp": "—",
                "collected_at": "—",
                "reason": asset.get("reason", "منبع پیکربندی نشده."),
                "analysis": {"status": "unavailable"}
            })

    registry_path = ROOT / "config" / "analysis_sources.json"
    registry_data = load_source_registry(registry_path) if registry_path.exists() else {"sources": []}
    source_registry = summarize_source_registry(registry_data) if registry_path.exists() else {}

    news_config_path = ROOT / "config" / "news_sources.json"
    configured_news_sources = load_json(news_config_path).get("sources", []) if news_config_path.exists() else []
    # The 100-source registry is the single authority for activation and access method.
    news_sources = merge_active_rss_sources(configured_news_sources, registry_data)
    news = collect_news(news_sources, settings.get("news", {}))
    known_symbols = [item["symbol"] for category in ("forex", "commodities", "crypto") for item in assets.get(category, []) if item.get("enabled")]
    analysis_candidates = extract_analysis_candidates(news, known_symbols)
    analysis_candidates = annotate_analysis_candidates(analysis_candidates, registry_data)
    directional_evidence = summarize_directional_evidence(analysis_candidates)
    # Verified public official APIs add slow macro context and ECB reference-rate cross-checks.
    official_macro = [
        fetch_ecb_reference_rates(timeout=int(settings.get("official_data", {}).get("timeout_seconds", 15))),
        fetch_world_bank_inflation(timeout=int(settings.get("official_data", {}).get("timeout_seconds", 20))),
        fetch_bls_macro(timeout=int(settings.get("official_data", {}).get("timeout_seconds", 25))),
        fetch_cftc_cot(timeout=int(settings.get("official_data", {}).get("timeout_seconds", 25))),
    ]
    forex_symbols = [item["symbol"] for item in assets.get("forex", []) if item.get("enabled")]
    local_now = datetime.now(ZoneInfo(settings.get("timezone", "Asia/Tehran")))
    report = render_report(results, settings, local_now, news=news, source_registry=source_registry, analysis_candidates=analysis_candidates, forex_symbols=forex_symbols, directional_evidence=directional_evidence, official_macro=official_macro)
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    out = report_dir / f"{local_now:%Y-%m-%d}.md"
    out.write_text(report, encoding="utf-8")
    print(f"News items collected: {len(news)}")
    print(f"Analysis candidates extracted: {len(analysis_candidates)}")
    print(f"Report written: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
