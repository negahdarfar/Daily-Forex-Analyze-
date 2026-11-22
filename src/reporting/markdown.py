from __future__ import annotations

from datetime import datetime


def render_report(results: list[dict], settings: dict, local_now: datetime, news: list[dict] | None = None, source_registry: dict | None = None, analysis_candidates: list[dict] | None = None, forex_symbols: list[str] | None = None, directional_evidence: dict | None = None) -> str:
    news = news or []
    source_registry = source_registry or {}
    analysis_candidates = analysis_candidates or []
    forex_symbols = set(forex_symbols or [])
    directional_evidence = directional_evidence or {}
    date_text = local_now.strftime("%Y-%m-%d")
    lines = [
        f"# گزارش روزانه تحلیل بازار — {date_text}", "",
        f"> زمان تولید: {local_now.isoformat()} | منطقه زمانی: {settings.get('timezone', 'Asia/Tehran')}", "",
        "## خلاصه اجرایی", "",
        "این نسخه غربالگری چندعاملی تکنیکال (هم‌ترازی و شیب EMA، RSI، MACD، ADX/DI، شکست ساختار و حجم در صورت وجود) و گردآوری RSS عمومی را انجام می‌دهد. امتیازها احتمال موفقیت نیستند. Yahoo Finance ممکن است تأخیردار باشد؛ داده قدیمی از رتبه‌بندی ستاپ‌ها حذف می‌شود. Entry صرفاً قیمت مرجع غربالگری است، نه سفارش اجرایی.", "",
        "## پنج فرصت تکنیکال برتر (غربالگری، نه سیگنال اجرایی)", "",
        "| رتبه | دارایی | جهت | امتیاز چندعاملی | قیمت پایانی | RSI | ADX | ATR٪ | ورود مرجع | حد ضرر | هدف | R:R |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|"
    ]
    candidates = [
        r for r in results
        if r.get("status") == "available"
        and r.get("analysis", {}).get("status") == "ok"
        and r["analysis"].get("direction") != "neutral"
        and r["analysis"].get("score", 0) >= float(settings.get("ranking", {}).get("minimum_setup_score", 55))
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
        lines.append("| — | ستاپ واجد شرایط با داده تازه یافت نشد | — | — | — | — | — | — | — | — |")

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
    lines += ["", "## ده جفت‌ارز برتر برای بررسی ورود (رتبه‌بندی تکنیکال موقت)", ""]
    lines.append("این رتبه‌بندی فقط از قدرت روند EMA، وضعیت RSI و تازگی داده روزانه ساخته شده است. تا زمانی که داده بنیادی/تقویم معتبر به موتور متصل و ارزیابی نشود، این جدول «رتبه ورود بنیادی+تکنیکال» یا توصیه معامله محسوب نمی‌شود.")
    lines += ["", "| رتبه | جفت‌ارز | جهت تکنیکال | امتیاز غربالگری | قیمت | RSI | Entry مرجع | SL | TP | R:R | عمر داده (ساعت) |", "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for rank, item in enumerate(fx_candidates[:10], 1):
        a = item["analysis"]
        fmt = lambda x: f"{x:.5f}" if isinstance(x, (int, float)) else "—"
        lines.append(
            f"| {rank} | {item['asset']} | {a['direction']} | {fx_rank(item)[0]:.1f} | "
            f"{fmt(a.get('close'))} | {fmt(a.get('rsi14'))} | {fmt(a.get('entry'))} | "
            f"{fmt(a.get('stop_loss'))} | {fmt(a.get('take_profit'))} | {fmt(a.get('risk_reward'))} | {item.get('age_hours','—')} |"
        )
    if not fx_candidates:
        lines.append("| — | جفت‌ارز واجد شرایط با داده تازه و جهت‌دار موجود نیست | — | — | — | — | — | — | — | — | — |")

    lines += ["", "## وضعیت داده دارایی‌ها", "",
              "| دارایی | منبع | وضعیت | آخرین timestamp بازار | زمان جمع‌آوری UTC | عمر داده (ساعت) | توضیح |",
              "|---|---|---|---|---|---:|---|"]
    for item in results:
        lines.append(
            f"| {item['asset']} | {item.get('provider','—')} | {item.get('status','—')} | "
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
                f"اعتبار منبع: {item['reliability']} | جمع‌آوری: {item['collected_at']} | "
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
        "", "## بازار ایران", "",
        "نرخ دلار/ریال، طلای ۱۸ عیار و تتر ایران تا زمان اتصال منبع محلی معتبر و timestampدار عمداً گزارش نشده‌اند.",
        "", "## روش‌شناسی و محدودیت‌ها", "",
        "- تایم‌فریم تکنیکال: روزانه؛ EMA، RSI قابل تنظیم و ATR.",
        "- امتیاز قاعده‌محور، احتمال موفقیت یا نرخ برد نیست.",
        "- Entry/SL/TP سطوح مکانیکی آموزشی بر اساس قیمت پایانی و ATR هستند؛ سفارش اجرایی نیستند.",
        "- داده قدیمی‌تر از آستانه پیکربندی‌شده از رتبه‌بندی حذف می‌شود، اما در جدول وضعیت داده باقی می‌ماند.",
        "- RSS عمومی گردآوری می‌شود؛ خبرها با فیلتر کلیدواژه‌ای اولیه به مرتبط با بازار/عمومی تقسیم می‌شوند. این فیلتر تحلیل معنایی یا تأیید صحت ادعا نیست.",
        "- رجیستری ۱۰۰ منبع مطابق اولویت کاربر مرتب شده است؛ در این نسخه فقط ۳ ورودی RSS موجود فعال‌اند و ۹۷ منبع دیگر به معنی اتصال خودکار نیستند.",
        "- وزن مرجعیت منبع، کیفیت تاریخی پیش‌بینی یا جهت قطعی ارز نیست؛ خبرهای تکراری از یک خبرگزاری/سیم خبری باید یک رویداد مستقل شمرده شوند.",
        "- جدول ده جفت‌ارز تا اتصال داده بنیادی و تقویم رویدادها، صرفاً رتبه‌بندی تکنیکال موقت است؛ داده stale یا جهت خنثی از آن حذف می‌شود.",
        "- FXStreet RSS در این نسخه با محدودیت استفاده غیرتجاری ثبت شده؛ متن کامل مقاله بازنشر یا ذخیره نمی‌شود.",
        "- شبکه‌های اجتماعی و منابع خصوصی بدون API یا مجوز scrape نمی‌شوند.",
        "- پیش از تصمیم معاملاتی باید اسپرد، لغزش، ساعات بازار، اخبار و داده زنده مستقل بررسی شوند.",
        "", "---", "Generated by Daily Market Analyze."
    ]
    return "\n".join(lines) + "\n"
