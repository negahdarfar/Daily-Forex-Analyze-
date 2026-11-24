from __future__ import annotations

from datetime import datetime, timezone


def render_report(results: list[dict], settings: dict, local_now: datetime, news: list[dict] | None = None, source_registry: dict | None = None, analysis_candidates: list[dict] | None = None, forex_symbols: list[str] | None = None, directional_evidence: dict | None = None, official_macro: list[dict] | None = None, market_intelligence: dict | None = None, opportunity_ranking: dict | None = None, opportunity_candidates: list[dict] | None = None, fx_ranking: dict | None = None, economic_calendar: dict | None = None, policy_rates: dict | None = None, currency_strength: dict | None = None) -> str:
    news = news or []
    source_registry = source_registry or {}
    analysis_candidates = analysis_candidates or []
    forex_symbols = set(forex_symbols or [])
    directional_evidence = directional_evidence or {}
    official_macro = official_macro or []
    market_intelligence = market_intelligence or {}
    opportunity_ranking = opportunity_ranking or {}
    opportunity_candidates = opportunity_candidates or []
    fx_ranking = fx_ranking or {}
    economic_calendar = economic_calendar or {}
    policy_rates = policy_rates or {}
    date_text = local_now.strftime("%Y-%m-%d")
    lines = [
        f"# گزارش روزانه تحلیل بازار — {date_text}", "",
        f"> زمان تولید: {local_now.isoformat()} | منطقه زمانی: {settings.get('timezone', 'Asia/Tehran')}", "",
        "## خلاصه اجرایی", "",
        "این نسخه غربالگری چندعاملی تکنیکال (هم‌ترازی و شیب EMA، RSI، MACD، ADX/DI، شکست ساختار و حجم در صورت وجود) و گردآوری RSS عمومی را انجام می‌دهد. امتیازها احتمال موفقیت نیستند. Yahoo Finance ممکن است تأخیردار باشد. کندل روزانه تا ۳۶ ساعت تازه، از ۳۶ تا ۹۶ ساعت صرفاً زمینه روند با برچسب تأخیری، و پس از ۹۶ ساعت نامعتبر است؛ تازگی قیمت برای فرصت‌های چندتایم‌فریمی جداگانه با کندل بسته‌شده ۱ساعته سنجیده می‌شود. Entry صرفاً قیمت مرجع غربالگری است، نه سفارش اجرایی.", "",
        "## غربالگری تکنیکال روزانه (بدون تأیید چندتایم‌فریمی)", "",
        "| رتبه | دارایی | جهت | امتیاز چندعاملی | قیمت پایانی | RSI | ADX | ATR٪ | ورود مرجع | حد ضرر | هدف | R:R |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    ]
    candidates = [
        r for r in results
        if r.get("status") == "available"
        and r.get("analysis", {}).get("status") == "ok"
        and r["analysis"].get("direction") != "neutral"
        and r["analysis"].get("score", 0) >= float(settings.get("ranking", {}).get("minimum_setup_score", 55))
        and r["analysis"].get("take_profit") is not None
        and r["analysis"].get("risk_reward") is not None
        and r["analysis"].get("risk_reward") >= 1.5
    ]
    candidates.sort(key=lambda r: r["analysis"].get("score", 0), reverse=True)
    for rank, item in enumerate(candidates[:int(settings["ranking"]["max_top_setups"])], 1):
        a = item["analysis"]
        fmt = lambda x: f"{x:.5f}" if isinstance(x, (int, float)) else "—"
        lines.append(
            f"| {rank} | {item['asset']} | {a['direction']} | {a['score']:.1f} | "
            f"{fmt(a.get('close'))} | {fmt(a.get('rsi14'))} | {fmt(a.get('adx'))} | "
            f"{fmt(a.get('atr_pct'))} | {fmt(a.get('entry'))} | {fmt(a.get('stop_loss'))} | "
            f"{fmt(a.get('take_profit'))} | {fmt(a.get('risk_reward'))} |"
        )
    if not candidates:
        lines.append("| — | ستاپ واجد شرایط با داده تازه یافت نشد | — | — | — | — | — | — | — | — | — | — |")

    # Daily FX shortlist is explicitly technical-only until fundamental evidence is ingested and scored.
    fx_candidates = [
        r for r in results
        if r.get("asset") in forex_symbols
        and r.get("status") == "available"
        and r.get("analysis", {}).get("status") == "ok"
        and r["analysis"].get("direction") != "neutral"
    ]
    def fx_rank(item):
        age = float(item.get("age_hours", 0.0))
        freshness = max(0.0, 1.0 - age / max(float(settings.get("max_quote_age_hours", 36)), 1.0))
        return (float(item["analysis"].get("score", 0.0)) * (0.70 + 0.30 * freshness), -age)
    fx_candidates.sort(key=fx_rank, reverse=True)
    lines += ["", "## غربال روزانه جفت‌ارزها (رتبه‌بندی تکنیکال موقت؛ نه فرصت ورود)", ""]
    lines.append("این رتبه‌بندی از امتیاز چندعاملی EMA، RSI، MACD، ADX/DI، ساختار و حجم در صورت وجود، با استفاده از آخرین کندل روزانه به‌عنوان زمینه روند ساخته شده است؛ سن آن در جدول وضعیت داده مشخص می‌شود و تازگی قیمت ورود با کندل بسته‌شده ۱ساعته کنترل می‌شود. تا زمانی که داده بنیادی/تقویم معتبر به موتور متصل و ارزیابی نشود، این جدول «رتبه ورود بنیادی+تکنیکال» یا توصیه معامله محسوب نمی‌شود.")
    lines += ["", "| رتبه | جفت‌ارز | جهت تکنیکال | امتیاز غربالگری | قیمت | RSI | ADX | ATR٪ | Entry مرجع | SL | TP | R:R | عمر داده (ساعت) |", "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for rank, item in enumerate(fx_candidates[:10], 1):
        a = item["analysis"]
        fmt = lambda x: f"{x:.5f}" if isinstance(x, (int, float)) else "—"
        lines.append(
            f"| {rank} | {item['asset']} | {a['direction']} | {fx_rank(item)[0]:.1f} | "
            f"{fmt(a.get('close'))} | {fmt(a.get('rsi14'))} | {fmt(a.get('adx'))} | {fmt(a.get('atr_pct'))} | "
            f"{fmt(a.get('entry'))} | {fmt(a.get('stop_loss'))} | {fmt(a.get('take_profit'))} | "
            f"{fmt(a.get('risk_reward'))} | {item.get('age_hours','—')} |"
        )
    if not fx_candidates:
        lines.append("| — | جفت‌ارز واجد شرایط با داده تازه و جهت‌دار موجود نیست | — | — | — | — | — | — | — | — | — |")

    # This is a shortlist, not the execution-qualified opportunity table above.
    lines += ["", "## رتبه‌بندی ترکیبی جفت‌ارزها — حداکثر ۱۰ مورد", ""]
    lines.append(
        "این جدول غربال پژوهشی مستقل از فرصت‌های فعال است. امتیاز فقط از حوزه‌هایی محاسبه می‌شود که شواهد واقعی آن‌ها در همین اجرا موجود است؛ پوشش ناقص کنار هر رتبه نمایش داده می‌شود. داده بنیادی نرخ/سورپرایز هم‌تراز و تقویم زمان‌دار هنوز به این رتبه‌بندی متصل نیستند؛ بنابراین هیچ ردیفی مجوز ورود معامله نیست."
    )
    lines.append(
        f"جفت‌ارزهای واجد شرایط جهت‌دار: {fx_ranking.get('eligible_directional_pairs', 0)}؛ "
        f"رتبه‌بندی‌شده: {fx_ranking.get('ranked_count', 0)}؛ "
        f"تقویم اقتصادی متصل: {'بله' if fx_ranking.get('coverage', {}).get('economic_calendar_connected') else 'خیر'}؛ "
        f"فاندامنتال در امتیاز نهایی: {'بله' if fx_ranking.get('coverage', {}).get('fundamental_integrated') else 'خیر'}."
    )
    lines += [
        "", "| رتبه | جفت‌ارز | جهت | امتیاز موقت | پوشش وزن | تکنیکال روزانه | هم‌ترازی ۱D/۴H/۱H | فاندامنتال | COT | خبر | نظر تحلیلگران | ریسک تقویم | عمر داده (ساعت) |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|"
    ]
    def fx_component(value):
        return f"{value:.1f}" if isinstance(value, (int, float)) else "—"
    for row in fx_ranking.get("opportunities", []):
        components = row.get("score_components", {})
        lines.append(
            f"| {row.get('rank')} | {row.get('symbol')} | {row.get('direction')} | "
            f"{fx_component(row.get('score'))} | {fx_component(row.get('score_coverage_pct'))}% | "
            f"{fx_component(components.get('technical'))} | {fx_component(components.get('mtf_confluence'))} | "
            f"{fx_component(components.get('fundamental'))} | {fx_component(components.get('cot_positioning'))} | {fx_component(components.get('news'))} | {fx_component(components.get('expert_consensus'))} | "
            f"{row.get('calendar_status', '—')} | {fx_component(row.get('data_age_hours'))} |"
        )
        if row.get("missing_evidence"):
            lines.append(f"  - شواهد ناقص: {', '.join(row.get('missing_evidence', []))}")
    if not fx_ranking.get("opportunities"):
        lines.append("| — | جفت‌ارز واجد شرایط برای رتبه‌بندی با داده تازه پیدا نشد | — | — | — | — | — | — | — | — | — | — | — |")
    lines.append("**محدودیت‌های قطعی این نسخه:** مؤلفه نرخ سیاستی BIS فقط proxy اختلاف carry و تغییر ۹۰روزه است؛ تورم/رشد/اشتغال و سورپرایزهای consensus هنوز محاسبه نمی‌شوند. تقویم متصل فقط رویدادهای پراثر آمریکا را پوشش می‌دهد و برای هفت ارز دیگر پوشش ندارد. نظرهای کارشناسی فقط از ناشران تخصصی فارکس و با حداقل دو ناشر مستقل وارد امتیاز می‌شوند. این امتیاز احتمال برد نیست.")

    lines += ["", "## قدرت نسبی هشت ارز — Currency Strength", ""]
    lines.append(
        f"وضعیت: {currency_strength.get('status', 'not_calculated')} | "
        f"تعداد جفت‌ارزهای دارای داده: {currency_strength.get('coverage_pairs', 0)} | "
        f"دوره محاسبه: {currency_strength.get('lookback_bars', '—')} کندل روزانه."
    )
    lines.append("| ارز | امتیاز نسبی | تغییر میانگین دوره (%) | تعداد جفت‌ارز | وضعیت |")
    lines.append("|---|---:|---:|---:|---|")
    for currency, row in currency_strength.get("currencies", {}).items():
        strength = row.get("strength_pct")
        score = row.get("relative_score")
        lines.append(
            f"| {currency} | {score if score is not None else '—'} | "
            f"{strength if strength is not None else '—'} | {row.get('pair_count', 0)} | {row.get('status', '—')} |"
        )
    lines.append(
        f"قوی‌ترین ارز: {currency_strength.get('strongest') or 'نامشخص'}؛ "
        f"ضعیف‌ترین ارز: {currency_strength.get('weakest') or 'نامشخص'}. "
        "این شاخص نسبی و توصیفی است، نه سیگنال مستقل ورود."
    )

    lines += ["", "## تقویم اقتصادی و فیلتر رویداد", ""]
    lines.append(
        f"منبع: {economic_calendar.get('source', '—')} | وضعیت: {economic_calendar.get('status', 'not_connected')} | "
        f"محدوده: {economic_calendar.get('coverage', '—')} | آخرین به‌روزرسانی: {economic_calendar.get('updated_at', '—')} | "
        f"سن داده: {economic_calendar.get('age_hours', '—')} ساعت."
    )
    lines.append(economic_calendar.get("data_note", "تقویم اقتصادی در این اجرا در دسترس نبود؛ ریسک رویداد نامشخص است."))
    if economic_calendar.get("attribution"):
        lines.append(f"انتساب منبع: {economic_calendar.get('attribution')}")
    lines.append(f"[تقویم XOOMAR]({economic_calendar.get('source_url', 'https://xoomar.com/markets/calendar')}) | [مستندات API]({economic_calendar.get('docs_url', 'https://xoomar.com/markets/api')}) | [شرایط استفاده]({economic_calendar.get('license_url', 'https://xoomar.com/terms')})")
    lines.append("این منبع فقط تقویم رویدادهای پراثر آمریکا را می‌دهد؛ پیش‌بینی اجماعی بازار را ارائه نمی‌کند. رویدادهای USD در پنجره ±۳۰ دقیقه به‌عنوان ریسک بالا علامت می‌خورند. برای EUR/GBP/JPY/CHF/CAD/AUD/NZD نبود رویداد در این فید به معنی نبود ریسک نیست.")
    future_events = []
    for event in (economic_calendar.get("events", []) if economic_calendar.get("status") == "available" else []):
        try:
            event_time = datetime.fromisoformat(str(event.get("scheduled_at_utc", "")).replace("Z", "+00:00"))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
            if event_time.astimezone(timezone.utc) >= datetime.now(timezone.utc):
                future_events.append(event)
        except (TypeError, ValueError):
            continue
    if future_events:
        lines += ["", "| زمان UTC | رویداد | اهمیت | دوره | مقدار قبلی | مقدار واقعی | پیش‌بینی |", "|---|---|---|---|---:|---:|---:|"]
        for event in future_events[:20]:
            lines.append(
                f"| {event.get('scheduled_at_utc')} | {event.get('name')} | {event.get('importance')} | "
                f"{event.get('period') or '—'} | {event.get('previous') or '—'} | "
                f"{event.get('actual') or '—'} | {event.get('forecast') or '—'} |"
            )
    else:
        lines.append("رویداد آینده‌ای در داده دریافت‌شده وجود ندارد یا تقویم قابل‌استفاده نیست؛ این وضعیت فقط با timestamp تازه منبع قابل تفسیر است.")

    lines += ["", "## نرخ سیاستی بانک‌های مرکزی — مؤلفه بنیادی", ""]
    lines.append(
        f"منبع: BIS WS_CBPOL | وضعیت پنل: {policy_rates.get('status', 'not_connected')} | "
        f"ارزهای تازه: {policy_rates.get('available_currency_count', 0)}/8 | "
        f"آخرین دریافت: {policy_rates.get('collected_at', '—')}."
    )
    lines.append(
        "امتیاز بنیادی فعلی فقط از اختلاف نرخ سیاستی و تغییر ۹۰روزه آن ساخته می‌شود؛ این یک proxy برای carry/جهت سیاست پولی است، نه تحلیل کامل تورم، رشد، اشتغال یا انتظارات بازار."
    )
    lines.append(f"[داده BIS]({policy_rates.get('source_url', 'https://stats.bis.org/api-doc/v2/')}) | [مستندات]({policy_rates.get('documentation_url', 'https://stats.bis.org/api-doc/v2/')}) | [شرایط استفاده]({policy_rates.get('license_url', 'https://data.bis.org/help/legal')})")
    rate_rows = policy_rates.get("rates", {})
    if rate_rows:
        lines += ["", "| ارز | حوزه BIS | نرخ سیاستی٪ | تغییر ۹۰روزه (واحد درصد) | آخرین تاریخ | عمر داده (روز) | وضعیت |", "|---|---|---:|---:|---|---:|---|"]
        for currency in ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"):
            row = rate_rows.get(currency, {})
            rate_value = row.get("policy_rate_pct")
            change_value = row.get("change_90d_pp")
            lines.append(
                f"| {currency} | {row.get('area_code', '—')} | "
                f"{fx_component(rate_value)} | {fx_component(change_value)} | "
                f"{row.get('latest_period', '—')} | {row.get('age_days', '—')} | {row.get('status', 'missing')} |"
            )
    else:
        lines.append("داده نرخ سیاستی در این اجرا دریافت نشد؛ امتیاز بنیادی برای جفت‌ارزها خالی می‌ماند.")
    lines.append(policy_rates.get("methodology_note", "نرخ سیاستی باید همراه با منابع رسمی بانک مرکزی و زمان انتشار بررسی شود."))

    lines += ["", "## وضعیت داده دارایی‌ها", "",
              "| دارایی | منبع | وضعیت | آخرین timestamp بازار | زمان جمع‌آوری UTC | عمر داده (ساعت) | توضیح |",
              "|---|---|---|---|---|---:|---|"]
    for item in results:
        lines.append(
            f"| {item['asset']} | {item.get('provider','—')} | {item.get('freshness_label', item.get('status','—'))} | "
            f"{item.get('market_timestamp','—')} | {item.get('collected_at','—')} | "
            f"{item.get('age_hours','—')} | {item.get('reason','—')} |"
        )

    lines += ["", "## پوشش رجیستری منابع تحلیلی", ""]
    if source_registry:
        lines.append(
            f"رجیستری شامل **{source_registry.get('total', 0)} منبع** در **{len(source_registry.get('categories', {}))} گروه** است؛ "
            f"در این نسخه **{source_registry.get('enabled', 0)} منبع** برای دریافت خودکار فعال‌اند، "
            f"{source_registry.get('permission_required', 0)} منبع نیازمند مجوز/API رسمی و "
            f"{source_registry.get('manual_only', 0)} منبع صرفاً برای بررسی دستی ثبت شده‌اند."
        )
        lines.append("ثبت یک منبع به معنی تأیید اعتبار آن یا مجوز جمع‌آوری خودکار نیست. امتیاز authority در رجیستری، وزن اولیه نوع/مرجعیت منبع است و با دقت تاریخی پیش‌بینی اشتباه نشود.")
        lines.append("رده‌های مرجعیت: " + ", ".join(f"{k}: {v}" for k, v in sorted(source_registry.get("authority_tiers", {}).items())) + ".")
        lines.append("ترتیب اولویت رجیستری: " + " ← ".join(source_registry.get("ordering_policy", [])) + ".")
        channels = source_registry.get("connection_channels", {})
        if channels:
            lines.append("روش‌های دسترسی ثبت‌شده: " + ", ".join(f"{k}: {v}" for k, v in sorted(channels.items())) + ".")
        roadmap = source_registry.get("next_integration_candidates", [])
        if roadmap:
            lines.append("اولویت‌های بعدی برای ارزیابی اتصال رسمی (هنوز متصل/تأییدشده محسوب نمی‌شوند):")
            for source in roadmap[:8]:
                lines.append(f"- رتبه {source.get('rank')}: {source.get('name')} — {source.get('category')} — {source.get('access_method')}")
        for category, count in sorted(source_registry.get("categories", {}).items()):
            lines.append(f"- {category}: {count} منبع")
    else:
        lines.append("رجیستری منابع در این اجرا بارگذاری نشد.")
    lines += ["", "## تحلیل‌های استخراج‌شده از منابع", ""]
    lines.append(f"تعداد مواردی که از تیتر/خلاصه RSS نشانه تحلیل داشته‌اند: **{len(analysis_candidates)}**. این‌ها ادعاهای منتشرشده‌اند، نه سیگنال تأییدشده.")
    if analysis_candidates:
        for item in analysis_candidates[:30]:
            assets_text = ", ".join(item.get("assets", [])) or "دارایی مشخص نشده"
            methods_text = ", ".join(item.get("methodologies", [])) or "روش مشخص نشده"
            frames_text = ", ".join(item.get("timeframes", [])) or "تایم‌فریم ذکر نشده"
            levels_text = ", ".join(f"{key}={value:g}" for key, value in item.get("levels", {}).items()) or "سطوح قیمتی ذکر نشده"
            direction_text = item.get("direction", "not_stated")
            lines.append(f"- **{item.get('title', 'بدون عنوان')}** — {item.get('source', '—')} | نویسنده: {item.get('author', 'not_provided')}")
            lines.append(f"  - دارایی: {assets_text} | جهت صریح: {direction_text} | تایم‌فریم: {frames_text}")
            lines.append(f"  - روش‌های ذکرشده: {methods_text} | سطوح استخراج‌شده: {levels_text}")
            lines.append(f"  - مرجعیت منبع: {item.get('source_authority_score', 0)}/100 ({item.get('source_reliability_tier', 'unmatched')}) | وضعیت: {item.get('verification_status', 'unverified')} | انتشار: {item.get('published_at', 'unknown')} | [متن اصلی]({item.get('url', '')})")
    else:
        lines.append("در این اجرا از خلاصه‌های RSS موردی با شواهد کافی برای استخراج تحلیل پیدا نشد.")
    lines += ["", "## جهت‌گیری بنیادی/تحلیلی وزن‌دهی‌شده بر اساس مرجعیت منبع", ""]
    lines.append("فقط جهت‌هایی وارد این بخش می‌شوند که در تیتر/خلاصه به‌صراحت بیان شده باشند. وزن هر ناشر از مرجعیت اولیه منبع می‌آید؛ ناشر تکراری برای هر دارایی و هر جهت فقط یک‌بار شمرده می‌شود. این وزن‌ها احتمال یا اجماع قطعی نیستند.")
    if directional_evidence:
        lines += ["", "| دارایی | وزن صعودی | وزن نزولی | انحراف خالص نرمال‌شده | ناشران صعودی | ناشران نزولی |", "|---|---:|---:|---:|---:|---:|"]
        for asset, evidence in sorted(directional_evidence.items(), key=lambda pair: abs(pair[1].get("net_bias", 0)), reverse=True):
            lines.append(f"| {asset} | {evidence['bullish_weight']:.1f} | {evidence['bearish_weight']:.1f} | {evidence['net_bias']:+.3f} | {evidence['bullish_publishers']} | {evidence['bearish_publishers']} |")
    else:
        lines.append("در این اجرا شواهد جهت‌دار صریح و قابل‌وزن‌دهی از منابع فعال پیدا نشد؛ جهت بنیادی نامشخص است و نباید از سکوت منابع، جهت بازار استنباط شود.")
    lines += ["", "## داده‌های رسمی کلان و نرخ مرجع", ""]
    for dataset in official_macro:
        lines.append(f"### {dataset.get('source', 'Official source')} — وضعیت: {dataset.get('status', 'unknown')}")
        lines.append(dataset.get("data_note", dataset.get("reason", "توضیحی ثبت نشده.")))
        observations = dataset.get("observations", [])
        if observations:
            if dataset.get("source") == "European Central Bank":
                lines.append("| ارز | نرخ مرجع به ازای هر یورو | تاریخ داده |")
                lines.append("|---|---:|---|")
                for obs in observations:
                    lines.append(f"| {obs.get('currency')} | {obs.get('value')} | {obs.get('data_timestamp')} |")
            elif dataset.get("source") == "World Bank":
                lines.append("| کشور | تورم سالانه CPI (%) | سال داده |")
                lines.append("|---|---:|---:|")
                for obs in observations:
                    lines.append(f"| {obs.get('country')} ({obs.get('country_code')}) | {obs.get('value')} | {obs.get('data_timestamp')} |")
            elif dataset.get("source") == "US Bureau of Labor Statistics":
                lines.append("| شاخص آمریکا | مقدار اخیر | دوره | مقدار قبلی | تغییر | واحد |")
                lines.append("|---|---:|---|---:|---:|---|")
                for obs in observations:
                    latest = obs.get("latest") or {}
                    previous = obs.get("previous") or {}
                    lines.append(f"| {obs.get('name')} | {latest.get('value','—')} | {latest.get('period_name')} {latest.get('year')} | {previous.get('value','—')} | {obs.get('change_from_previous','—')} | {obs.get('unit')} |")
            elif dataset.get("source") == "FRED":
                lines.append("| سری | مقدار اخیر | تاریخ | مقدار قبلی | تاریخ قبلی | تغییر | واحد | تناوب |")
                lines.append("|---|---:|---|---:|---|---:|---|---|")
                for obs in observations:
                    latest = obs.get("latest") or {}
                    previous = obs.get("previous") or {}
                    lines.append(f"| {obs.get('name')} ({obs.get('series_id')}) | {latest.get('value','—')} | {latest.get('date','—')} | {previous.get('value','—') if previous else '—'} | {previous.get('date','—') if previous else '—'} | {obs.get('change_from_previous') if obs.get('change_from_previous') is not None else '—'} | {obs.get('unit')} | {obs.get('frequency')} |")
                for error in dataset.get("errors", []):
                    lines.append(f"- سری {error.get('series_id')} در دسترس نبود: {error.get('reason')}")
            elif dataset.get("source") == "CFTC":
                lines.append("| قرارداد | تاریخ گزارش | خالص موقعیت غیرتجاری | درصد از OI | صدک ۵۲ هفته | Z-score | تغییر ۴ هفته‌ای (% OI) | تعداد هفته |")
                lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
                for obs in observations:
                    lines.append(f"| {obs.get('contract')} | {obs.get('report_date')} | {obs.get('noncommercial_net')} | {obs.get('noncommercial_net_pct_open_interest')}% | {obs.get('net_position_52w_percentile') if obs.get('net_position_52w_percentile') is not None else '—'} | {obs.get('net_position_52w_zscore') if obs.get('net_position_52w_zscore') is not None else '—'} | {obs.get('net_position_change_4w_pct_oi') if obs.get('net_position_change_4w_pct_oi') is not None else '—'} | {obs.get('history_weeks')} |")
        elif dataset.get("reason"):
            lines.append(f"خطای اتصال: {dataset.get('reason')}")
        lines.append(f"زمان جمع‌آوری UTC: {dataset.get('collected_at', 'unknown')}")
    lines.append("این داده‌ها زمینه کلان و موقعیت‌گیری هستند، نه قیمت اجرایی یا سیگنال مستقل: نرخ ECB مرجع است؛ تورم World Bank سالانه است؛ داده‌های BLS ماهانه و قابل بازبینی‌اند؛ FRED شامل نرخ سیاستی/بازده اوراق و داده‌های کلان است؛ COT هفتگی و با تاریخ موقعیت سه‌شنبه منتشر می‌شود.")
    lines += ["", "## اخبار و رویدادهای گردآوری‌شده (RSS عمومی)", ""]
    valid_news = [n for n in news if n.get("status") != "source_error"]
    relevant_news = [n for n in valid_news if n.get("relevance") == "market_relevant"]
    general_news = [n for n in valid_news if n.get("relevance") != "market_relevant"]
    errors = [n for n in news if n.get("status") == "source_error"]
    if relevant_news:
        lines.append(f"تعداد خبرهای مرتبط با بازار: {len(relevant_news)} از {len(valid_news)} خبر دریافت‌شده.")
        for item in relevant_news[:40]:
            lines.append(
                f"- **{item['title']}** — {item['source']} | انتشار: {item['published_at']} | "
                f"اعتبار منبع: {item['reliability']} | سنتیمنت تیتر: {item.get('sentiment', {}).get('label', 'not_scored')} | جمع‌آوری: {item['collected_at']} | "
                f"[منبع]({item['url']})"
            )
            if item.get("summary"):
                lines.append(f"  - {item['summary']}")
    else:
        lines.append("خبر مرتبط با بازار در این اجرا شناسایی نشد؛ این به معنی نبود خبر نیست.")
    if general_news:
        lines += ["", f"### اخبار عمومی کسب‌وکار کنارگذاشته‌شده از تحلیل بازار ({len(general_news)} مورد)", ""]
        lines.append("این خبرها دریافت شدند اما با کلیدواژه‌های فعلی ارتباط کافی با بازارهای هدف نداشتند؛ برای جلوگیری از شلوغی گزارش در رتبه‌بندی خبری استفاده نشدند.")
    if errors:
        lines += ["", "### خطاهای منابع RSS", ""]
        for item in errors:
            lines.append(f"- {item['source']}: {item['summary']}")

    lines += [
        "", "## تحلیلگران و تریدرها", "",
        "هیچ فردی بدون شواهد مستقل، نمونه کافی و ممیزی سوابق به‌عنوان تحلیلگر یا تریدر برتر معرفی نمی‌شود. تعداد دنبال‌کننده یا win rate ادعایی به‌تنهایی معیار نیست.",
        "", "## دیدگاه‌های بنیادی و سنتیمنت", "",
        "استخراج اولیه تحلیل فقط از تیتر و خلاصه RSS و با قواعد صریح انجام می‌شود؛ هنوز خواندن کامل صفحات، داوری معنایی موافق/مخالف یا سنجش عملکرد تاریخی تحلیلگر فعال نیست.",
    ]
    lines += ["", "## موتور هوشمند چندمنبعی و قدرت نسبی ارزها", ""]
    coverage = market_intelligence.get("coverage", {})
    lines.append("این بخش فقط شواهدی را ترکیب می‌کند که در همین اجرا واقعاً دریافت شده‌اند. حوزه‌های غایب حذف و وزن حوزه‌های موجود مجدداً نرمال می‌شود؛ داده مفقود تأیید خنثی محسوب نمی‌شود.")
    lines.append(
        f"پوشش اجرا: {coverage.get('fresh_fx_pairs_with_direction', 0)} جفت‌ارز تازه جهت‌دار؛ "
        f"{coverage.get('stale_fx_pairs', 0)} جفت‌ارز قدیمی؛ {coverage.get('news_items_received', 0)} خبر؛ "
        f"{coverage.get('currencies_with_cot_zscore', 0)} ارز دارای COT معتبر؛ "
        f"{coverage.get('duplicate_news_items_removed', 0)} خبر تکراری حذف‌شده؛ "
        f"{coverage.get('macro_datasets_available', 0)} از {coverage.get('macro_datasets_total', 0)} مجموعه کلان."
    )
    currency_rows = market_intelligence.get("currency_strength", [])
    if currency_rows:
        lines += ["", "### قدرت نسبی ارزها", "", "| ارز | امتیاز ترکیبی | تکنیکال نسبی | نمونه جفت‌ارز | COT | سرنخ خبری | حوزه‌های استفاده‌شده |", "|---|---:|---:|---:|---:|---:|---|"]
        for row in currency_rows:
            fmt = lambda value: f"{value:.1f}" if isinstance(value, (int, float)) else "—"
            lines.append(f"| {row.get('currency')} | {fmt(row.get('score'))} | {fmt(row.get('technical_score'))} | {row.get('technical_pair_samples', 0)} | {fmt(row.get('cot_score'))} | {fmt(row.get('news_score'))} ({row.get('news_items', 0)}) | {', '.join(row.get('domains_used', [])) or 'شواهد ناکافی'} |")
    pair_rows = market_intelligence.get("pair_confluence", [])
    if pair_rows:
        lines += ["", "### هم‌سویی قدرت ارزها با جهت تکنیکال", "", "| جفت‌ارز | قدرت پایه | قدرت مظنه | اختلاف | جهت ترکیبی | جهت تکنیکال | هم‌سویی |", "|---|---:|---:|---:|---|---|---|"]
        for row in pair_rows[:15]:
            lines.append(f"| {row.get('pair')} | {row.get('base_score'):.1f} | {row.get('quote_score'):.1f} | {row.get('strength_spread'):.1f} | {row.get('ensemble_direction')} | {row.get('technical_direction')} | {row.get('confluence')} |")
    method = market_intelligence.get("methodology", {})
    lines.append("وزن‌های پایه: " + ", ".join(f"{key}={value:.0%}" for key, value in method.get("weights", {}).items()) + ".")
    lines.append("محدودیت: " + method.get("limitations", "—"))
    lines.append("امتیاز ترکیبی احتمال برد یا دستور معامله نیست؛ تأیید چندتایم‌فریمی، اسپرد، تقویم رویداد و بک‌تست همچنان لازم است.")

    lines += [
        "", "## بازار ایران", "",
        "USD/IRR آزاد، USD/IRT آزاد، BTC/IRT، ETH/IRT و طلای محلی تا اتصال منبع معتبر، مجاز و timestampدار غیرفعال‌اند. ریال و تومان یا USD و USDT با هم ادغام نمی‌شوند.",
        "", "## روش‌شناسی و محدودیت‌ها", "",
        "- غربال اولیه قدیمی روزانه بر پایه EMA، RSI و ATR است؛ رتبه‌بندی فرصت‌های جدید جداگانه با تأیید ۱D/۴H/۱H انجام می‌شود.",
        "- امتیاز قاعده‌محور، احتمال موفقیت یا نرخ برد نیست.",
        "- Entry/SL/TP سطوح مکانیکی آموزشی بر اساس قیمت پایانی و ATR هستند؛ سفارش اجرایی نیستند.",
        "- داده قدیمی‌تر از آستانه پیکربندی‌شده از رتبه‌بندی حذف می‌شود، اما در جدول وضعیت داده باقی می‌ماند.",
        "- RSS عمومی گردآوری می‌شود؛ خبرها با فیلتر کلیدواژه‌ای اولیه به مرتبط با بازار/عمومی تقسیم می‌شوند. این فیلتر تحلیل معنایی یا تأیید صحت ادعا نیست.",
        "- رجیستری ۱۰۰ منبع ثبت شده است؛ ۹ ورودی/روش دسترسی فعال در رجیستری وجود دارد و ۹۱ منبع دیگر هنوز متصل نیستند. ثبت منبع به معنی دریافت موفق در هر اجرا نیست.",
        "- وزن مرجعیت منبع، کیفیت تاریخی پیش‌بینی یا جهت قطعی ارز نیست؛ خبرهای تکراری از یک خبرگزاری/سیم خبری باید یک رویداد مستقل شمرده شوند.",
        "- جدول ده جفت‌ارز تا اتصال داده بنیادی و تقویم رویدادها، صرفاً رتبه‌بندی تکنیکال موقت است؛ داده stale یا جهت خنثی از آن حذف می‌شود.",
        "- FXStreet RSS در این نسخه با محدودیت استفاده غیرتجاری ثبت شده؛ متن کامل مقاله بازنشر یا ذخیره نمی‌شود.",
        "- شبکه‌های اجتماعی و منابع خصوصی بدون API یا مجوز scrape نمی‌شوند.",
        "- پیش از تصمیم معاملاتی باید اسپرد، لغزش، ساعات بازار، اخبار و داده زنده مستقل بررسی شوند.",
        "", "---"
    ]
    lines += [
        "", "## حداکثر ۱۰ فرصت واجد شرایط — تأیید ۱D / ۴H / ۱H", "",
        "فقط وضعیت active در جدول رتبه‌بندی می‌شود. فرصت‌های conditional و watchlist جدا می‌مانند؛ کمتر از ۱۰ مورد نتیجه معتبر است.",
        f"تعداد فرصت فعال: {opportunity_ranking.get('count', 0)} | مشروط: {opportunity_ranking.get('conditional_count', 0)} | پایش: {opportunity_ranking.get('watchlist_count', 0)} | غیرقابل رتبه‌بندی: {opportunity_ranking.get('unrankable_count', 0)}",
        f"بررسی همبستگی: {opportunity_ranking.get('correlation_checked_count', 0)} مورد | داده همبستگی ناکافی: {opportunity_ranking.get('correlation_unavailable_count', 0)} | مجموع جریمه تنوع: {opportunity_ranking.get('total_diversification_penalty_points', 0)} امتیاز",
        "", "| رتبه | نماد | جهت | ستاپ | ورود | حد ضرر | هدف | R/R خالص | امتیاز خام | امتیاز تعدیل‌شده | بیشینه همبستگی |", "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|"
    ]
    ranked = opportunity_ranking.get("opportunities", [])
    if ranked:
        for item in ranked:
            target = item.get("targets", [{}])[0].get("price") if item.get("targets") else None
            entry = item.get("entry_trigger", {}).get("close")
            fmt = lambda value: f"{value:.6f}" if isinstance(value, (int, float)) else "—"
            lines.append(
                f"| {item.get('rank')} | {item.get('symbol')} | {item.get('direction')} | "
                f"{item.get('setup_type')} | {fmt(entry)} | {fmt(item.get('stop_loss'))} | "
                f"{fmt(target)} | {fmt(item.get('net_rr'))} | {fmt(item.get('score_raw'))} | "
                f"{fmt(item.get('score_adjusted'))} | {fmt(item.get('max_abs_correlation_to_higher_ranked'))} |"
            )
    else:
        lines.append("| — | در این اجرا فرصت فعالِ دارای داده، هزینه و شواهد کافی تأیید نشد | — | — | — | — | — | — | — | — | — |")
    conditional = [item for item in opportunity_candidates if item.get("status") == "conditional"]
    watchlist = [item for item in opportunity_candidates if item.get("status") == "watchlist"]
    if conditional:
        lines += ["", "### فرصت‌های مشروط — هنوز قابل معامله/رتبه‌بندی فعال نیستند", ""]
        for item in conditional[:20]:
            lines.append(f"- **{item.get('symbol')}** ({item.get('direction') or 'جهت نامشخص'} / {item.get('setup_type') or 'بدون ستاپ'}): کمبودها: {', '.join(item.get('missing_evidence', [])) or '—'}؛ هشدارها: {', '.join(item.get('risk_flags', [])) or '—'}.")
    if watchlist:
        lines += ["", "### فهرست پایش", ""]
        for item in watchlist[:20]:
            lines.append(f"- **{item.get('symbol')}**: {', '.join(item.get('risk_flags', [])) or 'شرط ورود هنوز تأیید نشده'}.")
    unrankable = [item for item in opportunity_candidates if item.get("status") == "unrankable"]
    if unrankable:
        lines += ["", "### نمادهای غیرقابل رتبه‌بندی به‌دلیل نقص داده", ""]
        for item in unrankable[:25]:
            reasons = item.get("risk_flags", []) + item.get("missing_evidence", [])
            lines.append(f"- **{item.get('symbol')}**: {', '.join(reasons) or 'داده کافی در دسترس نیست'}.")
    lines += [
        "", "### محدودیت اجرایی", "",
        "تا وقتی هزینه رفت‌وبرگشت اختصاصی هر ابزار، نقدشوندگی، شواهد بنیادی و خبری و کیفیت منبع به‌صورت عددی و قابل‌ردیابی پیکربندی/تأیید نشوند، فرصت به وضعیت active ارتقا نمی‌یابد. داده روزانه یا قیمت Yahoo به‌تنهایی قیمت اجرایی بروکر محسوب نمی‌شود. حالت سفارش واقعی غیرفعال است.",
    ]

    lines.append("Generated by Daily Market Analyze.")
    return "\n".join(lines) + "\n"
