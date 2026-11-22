from __future__ import annotations

from datetime import datetime


def render_report(results: list[dict], settings: dict, local_now: datetime, news: list[dict] | None = None, source_registry: dict | None = None) -> str:
    news = news or []
    source_registry = source_registry or {}
    date_text = local_now.strftime("%Y-%m-%d")
    lines = [
        f"# گزارش روزانه تحلیل بازار — {date_text}", "",
        f"> زمان تولید: {local_now.isoformat()} | منطقه زمانی: {settings.get('timezone', 'Asia/Tehran')}", "",
        "## خلاصه اجرایی", "",
        "این نسخه غربالگری تکنیکال و گردآوری RSS عمومی را انجام می‌دهد. Yahoo Finance ممکن است تأخیردار باشد؛ داده قدیمی از رتبه‌بندی ستاپ‌ها حذف می‌شود. این گزارش توصیه قطعی معامله نیست.", "",
        "## پنج فرصت تکنیکال برتر (غربالگری، نه سیگنال اجرایی)", "",
        "| رتبه | دارایی | جهت | امتیاز قاعده‌محور | قیمت پایانی | RSI | ورود مکانیکی | حد ضرر | هدف | R:R |",
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
            f"{fmt(a.get('close'))} | {fmt(a.get('rsi14'))} | {fmt(a.get('entry'))} | "
            f"{fmt(a.get('stop_loss'))} | {fmt(a.get('take_profit'))} | {fmt(a.get('risk_reward'))} |"
        )
    if not candidates:
        lines.append("| — | ستاپ واجد شرایط با داده تازه یافت نشد | — | — | — | — | — | — | — | — |")

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
        lines.append("ثبت یک منبع به معنی تأیید اعتبار آن یا مجوز جمع‌آوری خودکار نیست. امتیاز اعتبار همه منابع تا زمان ارزیابی مستقل `unassessed` است.")
        for category, count in sorted(source_registry.get("categories", {}).items()):
            lines.append(f"- {category}: {count} منبع")
    else:
        lines.append("رجیستری منابع در این اجرا بارگذاری نشد.")
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
        "RSS در این مرحله فقط خبرها را گردآوری می‌کند؛ هنوز تحلیل معنایی، استخراج دیدگاه صعودی/نزولی یا تشخیص اجماع مخالف/موافق فعال نیست. تیتر خبر به‌تنهایی توصیه یا جهت معامله محسوب نمی‌شود.",
        "", "## بازار ایران", "",
        "نرخ دلار/ریال، طلای ۱۸ عیار و تتر ایران تا زمان اتصال منبع محلی معتبر و timestampدار عمداً گزارش نشده‌اند.",
        "", "## روش‌شناسی و محدودیت‌ها", "",
        "- تایم‌فریم تکنیکال: روزانه؛ EMA، RSI قابل تنظیم و ATR.",
        "- امتیاز قاعده‌محور، احتمال موفقیت یا نرخ برد نیست.",
        "- Entry/SL/TP سطوح مکانیکی آموزشی بر اساس قیمت پایانی و ATR هستند؛ سفارش اجرایی نیستند.",
        "- داده قدیمی‌تر از آستانه پیکربندی‌شده از رتبه‌بندی حذف می‌شود، اما در جدول وضعیت داده باقی می‌ماند.",
        "- RSS عمومی گردآوری می‌شود؛ خبرها با فیلتر کلیدواژه‌ای اولیه به مرتبط با بازار/عمومی تقسیم می‌شوند. این فیلتر تحلیل معنایی یا تأیید صحت ادعا نیست.",
        "- رجیستری ۱۰۰ منبع، فهرست کشف و ارزیابی است؛ به معنی اتصال ۱۰۰ منبع نیست. فقط منابع دارای روش دسترسی مستند فعال می‌شوند.",
        "- FXStreet RSS در این نسخه با محدودیت استفاده غیرتجاری ثبت شده؛ متن کامل مقاله بازنشر یا ذخیره نمی‌شود.",
        "- شبکه‌های اجتماعی و منابع خصوصی بدون API یا مجوز scrape نمی‌شوند.",
        "- پیش از تصمیم معاملاتی باید اسپرد، لغزش، ساعات بازار، اخبار و داده زنده مستقل بررسی شوند.",
        "", "---", "Generated by Daily Market Analyze."
    ]
    return "\n".join(lines) + "\n"
