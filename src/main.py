from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

from src.data.market_data import fetch_asset_history
from src.data.news import collect_news
from src.data.official_data import fetch_ecb_reference_rates, fetch_world_bank_inflation, fetch_bls_macro, fetch_cftc_cot, fetch_fred_public_series
from src.data.economic_calendar import fetch_us_economic_calendar
from src.data.policy_rates import fetch_bis_policy_rates
from src.data.source_registry import load_source_registry, summarize_source_registry, annotate_analysis_candidates, summarize_directional_evidence, merge_active_rss_sources
from src.experts.analysis_ingestion import extract_analysis_candidates
from src.reporting.markdown import render_report
from src.technical.indicators import analyze
from src.analysis.market_intelligence import build_market_intelligence
from src.analysis.fx_ranker import rank_fx_pairs
from src.analysis.opportunity_engine import build_opportunity, rank_opportunities, resample_completed_4h, completed_hourly_candles
from src.analysis.currency_strength import calculate_currency_strength
from src.analysis.market_structure import analyze_market_structure

ROOT = Path(__file__).resolve().parents[1]


def daily_context_is_usable(
    daily_status: str | None,
    daily_age_hours: float | None,
    max_daily_age_hours: float,
    hourly_status: str | None,
    hourly_quote_age_minutes: float | None,
    max_hourly_age_minutes: float,
) -> bool:
    """Validate slow daily context separately from the fresh intraday quote."""
    return (
        daily_status == "available"
        and daily_age_hours is not None
        and 0 <= float(daily_age_hours) <= max_daily_age_hours
        and hourly_status == "available"
        and hourly_quote_age_minutes is not None
        and 0 <= float(hourly_quote_age_minutes) <= max_hourly_age_minutes
    )


def classify_daily_context_age(age_hours: float | None, standard_limit_hours: float, maximum_context_hours: float) -> str:
    """Classify daily candles as fresh, delayed-but-usable context, or stale."""
    if age_hours is None or float(age_hours) < 0:
        return "stale"
    age = float(age_hours)
    if age <= standard_limit_hours:
        return "fresh"
    if age <= maximum_context_hours:
        return "delayed_context"
    return "stale"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    assets = load_json(ROOT / "config" / "assets.json")
    settings = load_json(ROOT / "config" / "settings.json")
    ranking_policy = load_json(ROOT / "config" / "ranking.json")
    risk_policy = load_json(ROOT / "config" / "risk.json")
    settings["ranking"].update({
        "max_top_setups": min(10, int(ranking_policy.get("max_opportunities", 10))),
        "minimum_net_rr": float(ranking_policy.get("minimum_net_rr", 2.0)),
        "weights": ranking_policy.get("weights", settings["ranking"].get("weights", {})),
    })
    settings["risk"].update({
        "minimum_net_rr": float(risk_policy.get("minimum_net_rr", settings["risk"].get("minimum_net_rr", 2.0))),
        "stop_atr_buffer": float(risk_policy.get("stop_atr_buffer", settings["risk"].get("stop_atr_buffer", 0.2))),
        "live_orders_enabled": bool(risk_policy.get("live_orders_enabled", False)),
        "mode": risk_policy.get("mode", settings["risk"].get("mode", "research_paper_trading_only")),
        "instrument_costs": risk_policy.get("instrument_costs", risk_policy.get("round_trip_cost_price_by_instrument", {})),
    })
    market_catalog = load_json(ROOT / "config" / "markets.json")
    market_by_symbol = {item["symbol"]: item for item in market_catalog.get("markets", [])}
    analysis_cutoff_utc = datetime.now(timezone.utc).isoformat()
    results = []
    opportunity_candidates = []
    daily_returns = {}
    enabled = []
    for category in ("forex", "commodities", "crypto"):
        enabled.extend(a for a in assets.get(category, []) if a.get("enabled"))

    # Fetch the daily and hourly datasets concurrently with a conservative worker cap.
    max_workers = max(1, min(8, int(settings.get("max_concurrent_market_fetches", 4))))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        fetch_futures = {
            asset["symbol"]: (
                executor.submit(
                    fetch_asset_history, asset,
                    period=settings.get("history_period", "6mo"),
                    interval=settings.get("history_interval", "1d"),
                    timeout=int(settings.get("market_data", {}).get("timeout_seconds", 10)),
                ),
                executor.submit(
                    fetch_asset_history, asset,
                    period=settings.get("intraday_history_period", "60d"),
                    interval="1h",
                    timeout=int(settings.get("market_data", {}).get("timeout_seconds", 10)),
                ),
            )
            for asset in enabled
        }
        fetched_data = {
            symbol: (daily_future.result(), hourly_future.result())
            for symbol, (daily_future, hourly_future) in fetch_futures.items()
        }

    for asset in enabled:
        fetched, hourly_fetched = fetched_data[asset["symbol"]]
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
                max_context_age = float(settings.get("max_daily_context_age_hours", 96))
                item["freshness_label"] = classify_daily_context_age(age_hours, max_age, max_context_age)
                if item["freshness_label"] == "stale":
                    item["status"] = "stale"
                    item["reason"] = f"سن کندل روزانه {item['age_hours']} ساعت است و از حد زمینه مجاز {max_context_age:.0f} ساعت عبور کرده؛ از رتبه‌بندی حذف شد."
                elif item["freshness_label"] == "delayed_context":
                    item["reason"] = f"کندل روزانه {item['age_hours']} ساعت عمر دارد؛ فقط زمینه روند است. تازگی قیمت با کندل بسته‌شده ۱ساعته جداگانه کنترل می‌شود."
        else:
            item["analysis"] = {"status": "unavailable"}
        # Intraday data is fetched independently; daily candles are never upsampled.
        hourly_frame = hourly_fetched.get("history") if hourly_fetched.get("status") == "available" else None
        daily_frame = fetched.get("history") if fetched.get("status") == "available" else None
        if daily_frame is not None and "Close" in daily_frame.columns:
            daily_returns[asset["symbol"]] = daily_frame["Close"].pct_change().dropna()
        # Freeze every timeframe at the same orchestration cutoff; exclude the still-forming 1H candle.
        cutoff_dt = datetime.fromisoformat(analysis_cutoff_utc.replace("Z", "+00:00"))
        hourly_frame = completed_hourly_candles(hourly_frame, now=cutoff_dt) if hourly_frame is not None else None
        four_hour_frame = resample_completed_4h(hourly_frame, now=cutoff_dt) if hourly_frame is not None else None
        frames = {"1d": daily_frame, "4h": four_hour_frame, "1h": hourly_frame}
        quote_stamp = (
            (hourly_frame.index[-1].to_pydatetime() + timedelta(hours=1)).isoformat()
            if hourly_frame is not None and not hourly_frame.empty else None
        )
        instrument_costs = settings.get("risk", {}).get("instrument_costs", {}).get(asset["symbol"])
        candidate = build_opportunity(
            asset["symbol"], frames, settings, costs=instrument_costs,
            quote_timestamp=quote_stamp,
            analysis_cutoff_utc=analysis_cutoff_utc,
            instrument={
                **market_by_symbol.get(asset["symbol"], {}),
                "market_session_status": "24x7_reference_market" if asset.get("category") == "crypto" else "provider_calendar_unverified",
                "provider": hourly_fetched.get("provider"),
                "provider_symbol": asset.get("yahoo"),
            },
        )
        candidate["market_structure"] = analyze_market_structure(hourly_frame) if hourly_frame is not None else {"status": "unavailable", "events": []}
        candidate["data_sources"] = {
            "daily": fetched.get("provider"),
            "hourly": hourly_fetched.get("provider"),
            "hourly_status": hourly_fetched.get("status"),
        }
        quote_age_minutes = None
        if hourly_fetched.get("status") == "available" and quote_stamp:
            quote_age_minutes = (
                cutoff_dt - datetime.fromisoformat(quote_stamp.replace("Z", "+00:00"))
            ).total_seconds() / 60
            candidate["quote_age_minutes"] = round(max(0.0, quote_age_minutes), 1)

        # A completed daily candle is a slow trend-context input, not the live quote.
        # Keep its age limit separate from the freshness gate on the completed 1H quote.
        daily_context_age = item.get("age_hours")
        daily_context_ok = daily_context_is_usable(
            daily_status=fetched.get("status"),
            daily_age_hours=daily_context_age,
            max_daily_age_hours=float(settings.get("max_daily_context_age_hours", 96)),
            hourly_status=hourly_fetched.get("status"),
            hourly_quote_age_minutes=quote_age_minutes,
            max_hourly_age_minutes=float(settings.get("max_intraday_quote_age_minutes", 180)),
        )
        candidate["daily_context_age_hours"] = daily_context_age
        if not daily_context_ok:
            candidate["status"] = "unrankable"
            if fetched.get("status") != "available" or daily_context_age is None or daily_context_age > float(settings.get("max_daily_context_age_hours", 96)):
                candidate["risk_flags"].append("daily_data_unavailable_or_context_too_old")
            if hourly_fetched.get("status") != "available":
                candidate["risk_flags"].append("hourly_data_unavailable")
            elif quote_age_minutes is None or quote_age_minutes > float(settings.get("max_intraday_quote_age_minutes", 180)):
                candidate["risk_flags"].append("hourly_quote_stale")
        elif daily_context_age is not None and daily_context_age > float(settings.get("max_quote_age_hours", 36)):
            candidate["risk_flags"].append("daily_context_older_than_standard_quote_limit_but_hourly_is_fresh")
        opportunity_candidates.append(candidate)

        results.append(item)
        print(f"{asset['symbol']}: {item['status']} | opportunity={candidate['status']}")

    for asset in assets.get("iran_local", []):
        if not asset.get("enabled"):
            results.append({
                "asset": asset["symbol"], "provider": "not_configured",
                "status": "unavailable", "market_timestamp": "—",
                "collected_at": "—",
                "reason": asset.get("reason", "منبع پیکربندی نشده."),
                "analysis": {"status": "unavailable"}
            })
            local_candidate = build_opportunity(
                asset["symbol"],
                {"1d": None, "4h": None, "1h": None},
                settings,
                instrument=market_by_symbol.get(asset["symbol"], {
                    "symbol": asset["symbol"], "category": "iran_local",
                    "execution_capability": "not_configured",
                }),
                analysis_cutoff_utc=analysis_cutoff_utc,
            )
            local_candidate["risk_flags"].append("local_market_data_source_not_configured")
            local_candidate["missing_evidence"].append("authorized_timestamped_local_quote_missing")
            opportunity_candidates.append(local_candidate)

    # Relative strength uses the same daily FX close histories already fetched in this run.
    fx_close_series = {}
    for fx_asset in assets.get("forex", []):
        symbol = fx_asset.get("symbol")
        fetched_pair = fetched_data.get(symbol, ({} , {}))[0]
        frame_pair = fetched_pair.get("history") if fetched_pair.get("status") == "available" else None
        if frame_pair is not None and "Close" in frame_pair.columns:
            fx_close_series[symbol] = frame_pair["Close"]
    currency_strength = calculate_currency_strength(
        fx_close_series,
        lookback=int(settings.get("currency_strength", {}).get("lookback_bars", 20)),
        min_pairs_per_currency=int(settings.get("currency_strength", {}).get("min_pairs_per_currency", 2)),
    )

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
        fetch_fred_public_series(timeout=int(settings.get("official_data", {}).get("timeout_seconds", 15))),
    ]
    # One low-frequency, no-key request; the adapter rejects stale snapshots.
    economic_calendar = fetch_us_economic_calendar(
        timeout=int(settings.get("economic_calendar", {}).get("timeout_seconds", 10)),
        max_age_hours=float(settings.get("economic_calendar", {}).get("max_age_hours", 24)),
    )
    policy_rates = fetch_bis_policy_rates(
        timeout=int(settings.get("policy_rates", {}).get("timeout_seconds", 20)),
        max_age_days=int(settings.get("policy_rates", {}).get("max_age_days", 14)),
        history_days=int(settings.get("policy_rates", {}).get("history_days", 400)),
    )
    forex_symbols = [item["symbol"] for item in assets.get("forex", []) if item.get("enabled")]
    local_now = datetime.now(ZoneInfo(settings.get("timezone", "Asia/Tehran")))
    market_intelligence = build_market_intelligence(
        results=results, news=news, official_macro=official_macro,
        analysis_candidates=analysis_candidates, source_registry=source_registry,
    )
    fx_ranking = rank_fx_pairs(
        results=results,
        market_intelligence=market_intelligence,
        directional_evidence=directional_evidence,
        economic_calendar=economic_calendar,
        policy_rates=policy_rates,
        opportunity_candidates=opportunity_candidates,
        policy=ranking_policy.get("fx_shortlist", {}),

        max_age_hours=float(settings.get("max_quote_age_hours", 36)),
    )
    opportunity_ranking = rank_opportunities(
        opportunity_candidates,
        max_items=int(settings.get("ranking", {}).get("max_top_setups", 10)),
        returns_by_symbol=daily_returns,
        correlation_threshold=float(settings.get("ranking", {}).get("correlation_threshold", 0.85)),
        correlation_penalty_points=float(settings.get("ranking", {}).get("correlation_penalty_points", 10.0)),
    )
    report = render_report(
        results, settings, local_now, news=news, source_registry=source_registry,
        analysis_candidates=analysis_candidates, forex_symbols=forex_symbols,
        directional_evidence=directional_evidence, official_macro=official_macro,
        market_intelligence=market_intelligence,
        opportunity_ranking=opportunity_ranking,
        opportunity_candidates=opportunity_candidates,
        fx_ranking=fx_ranking,
        economic_calendar=economic_calendar,
        policy_rates=policy_rates,
    )
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    out = report_dir / f"{local_now:%Y-%m-%d}.md"
    out.write_text(report, encoding="utf-8")
    json_out = report_dir / f"{local_now:%Y-%m-%d}-opportunities.json"
    json_out.write_text(json.dumps({
        "schema_version": "1.0.0",
        "analysis_cutoff_utc": analysis_cutoff_utc,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ranking": opportunity_ranking,
        "fx_ranking": fx_ranking,
        "economic_calendar": economic_calendar,
        "policy_rates": policy_rates,
        "candidates": opportunity_candidates,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"News items collected: {len(news)}")
    print(f"Analysis candidates extracted: {len(analysis_candidates)}")
    print(f"Report written: {out.relative_to(ROOT)}")
    print(f"Opportunity JSON written: {json_out.relative_to(ROOT)}")
    print(f"Execution-qualified opportunities: {opportunity_ranking['count']}")


if __name__ == "__main__":
    main()
