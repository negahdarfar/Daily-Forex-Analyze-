"""No-key BIS central-bank policy-rate panel for the eight major FX currencies."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from io import BytesIO, StringIO
from zipfile import BadZipFile, ZipFile
from typing import Any

import requests


BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.US+XM+GB+JP+CH+CA+AU+NZ"
CURRENCY_AREAS = {
    "USD": "US", "EUR": "XM", "GBP": "GB", "JPY": "JP",
    "CHF": "CH", "CAD": "CA", "AUD": "AU", "NZD": "NZ",
}


def _period_date(value: str) -> date | None:
    value = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    return None


def fetch_bis_policy_rates(
    timeout: int = 20,
    max_age_days: int = 14,
    history_days: int = 400,
) -> dict[str, Any]:
    """Fetch daily policy rates for eight currency areas in one BIS SDMX CSV request."""
    now = datetime.now(timezone.utc)
    start_period = (now.date() - timedelta(days=max(180, int(history_days)))).isoformat()
    try:
        response = requests.get(
            BIS_URL,
            params={"format": "csvfile", "startPeriod": start_period},
            headers={
                "User-Agent": "DailyForexAnalyze/1.0 (+https://github.com/negahdarfar/Daily-Forex-Analyze-)",
                "Accept": "text/csv",
            },
            timeout=max(1, int(timeout)),
        )
        response.raise_for_status()
        raw_content = response.content
        if raw_content.startswith(bytes((0x50, 0x4B, 0x03, 0x04))):
            try:
                with ZipFile(BytesIO(raw_content)) as archive:
                    csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                    if not csv_names:
                        raise ValueError("BIS CSV archive contains no CSV file")
                    raw_content = archive.read(csv_names[0])
            except BadZipFile as exc:
                raise ValueError("BIS returned an invalid CSV archive") from exc
        reader = csv.DictReader(StringIO(raw_content.decode("utf-8-sig")))
        required = {"REF_AREA", "TIME_PERIOD", "OBS_VALUE"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("BIS CSV is missing required SDMX columns")
        observations: dict[str, list[dict[str, Any]]] = {code: [] for code in CURRENCY_AREAS.values()}
        for raw in reader:
            area = str(raw.get("REF_AREA", "")).strip()
            if area not in observations:
                continue
            period = _period_date(raw.get("TIME_PERIOD", ""))
            try:
                value = float(str(raw.get("OBS_VALUE", "")).strip())
            except (TypeError, ValueError):
                continue
            if period is None:
                continue
            observations[area].append({
                "date": period,
                "value": value,
                "title": str(raw.get("TITLE", "")).strip(),
                "compilation": str(raw.get("COMPILATION", "")).strip(),
                "unit": str(raw.get("UNIT_MEASURE", "")).strip(),
                "observation_status": str(raw.get("OBS_STATUS", "")).strip(),
            })

        rates: dict[str, dict[str, Any]] = {}
        for currency, area in CURRENCY_AREAS.items():
            rows = sorted(observations.get(area, []), key=lambda row: row["date"])
            if not rows:
                rates[currency] = {"status": "missing", "area_code": area}
                continue
            latest = rows[-1]
            age_days = max(0, (now.date() - latest["date"]).days)
            target_date = latest["date"] - timedelta(days=90)
            prior_rows = [row for row in rows if row["date"] <= target_date]
            prior = prior_rows[-1] if prior_rows else rows[0]
            change_3m = (
                round(latest["value"] - prior["value"], 6)
                if prior["date"] < latest["date"] else None
            )
            fresh = age_days <= max(1, int(max_age_days))
            rates[currency] = {
                "status": "available" if fresh else "stale",
                "area_code": area,
                "policy_rate_pct": latest["value"],
                "latest_period": latest["date"].isoformat(),
                "age_days": age_days,
                "change_90d_pp": change_3m,
                "comparison_period": prior["date"].isoformat(),
                "series_title": latest["title"],
                "compilation": latest["compilation"],
                "unit": latest["unit"],
                "observation_status": latest["observation_status"],
                "observation_count": len(rows),
            }

        available = sum(1 for row in rates.values() if row.get("status") == "available")
        stale = sum(1 for row in rates.values() if row.get("status") == "stale")
        if available == len(CURRENCY_AREAS):
            status = "available"
        elif available:
            status = "partial"
        elif stale:
            status = "stale"
        else:
            status = "unavailable"
        return {
            "source": "Bank for International Settlements (BIS)",
            "dataflow": "WS_CBPOL",
            "status": status,
            "frequency": "daily",
            "scope": list(CURRENCY_AREAS),
            "collected_at": now.isoformat(),
            "start_period": start_period,
            "max_age_days": int(max_age_days),
            "available_currency_count": available,
            "stale_currency_count": stale,
            "rates": rates,
            "source_url": BIS_URL,
            "documentation_url": "https://stats.bis.org/api-doc/v2/",
            "license_url": "https://data.bis.org/help/legal",
            "methodology_note": (
                "Policy-rate carry and 90-day policy-rate change are macro proxies, not a complete "
                "fundamental forecast. Country-area policy instruments and publication timing can differ."
            ),
        }
    except Exception as exc:
        return {
            "source": "Bank for International Settlements (BIS)",
            "dataflow": "WS_CBPOL",
            "status": "source_error",
            "frequency": "daily",
            "scope": list(CURRENCY_AREAS),
            "collected_at": now.isoformat(),
            "rates": {},
            "reason": f"{type(exc).__name__}: {exc}",
            "source_url": BIS_URL,
            "documentation_url": "https://stats.bis.org/api-doc/v2/",
            "license_url": "https://data.bis.org/help/legal",
            "methodology_note": "No fundamental policy-rate score is available for this run.",
        }
