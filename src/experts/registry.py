"""قواعد ارزیابی تحلیلگران؛ ادعای بازاریابی معادل سابقه تأییدشده نیست."""
REQUIRED_EVIDENCE = (
    "independently_verifiable_track_record",
    "sample_size",
    "maximum_drawdown",
    "profit_factor",
    "expectancy",
    "average_risk_reward",
    "evaluation_period",
    "market_and_timeframe",
)


def assess_profile(profile: dict) -> dict:
    missing = [key for key in REQUIRED_EVIDENCE if not profile.get(key)]
    if missing:
        return {
            "status": "unverified",
            "missing_evidence": missing,
            "warning": "فالوئر، اسکرین‌شات انتخابی یا win rate ادعایی به‌تنهایی مدرک عملکرد نیست."
        }
    return {
        "status": "evidence_submitted_not_yet_audited",
        "missing_evidence": [],
        "warning": "وجود اطلاعات به معنی تأیید مستقل آن‌ها نیست؛ ممیزی منبع لازم است."
    }
