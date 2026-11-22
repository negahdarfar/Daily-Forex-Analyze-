from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.data.market_data import fetch_history
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
        symbol = asset["yahoo"]
        fetched = fetch_history(
            symbol,
            period=settings.get("history_period", "6mo"),
            interval=settings.get("history_interval", "1d")
        )
        item = {
            "asset": asset["symbol"],
            "provider": fetched.get("provider", "—"),
            "status": fetched.get("status", "unknown"),
            "market_timestamp": fetched.get("market_timestamp", "—"),
            "reason": fetched.get("reason", "—")
        }
        if fetched.get("status") == "available":
            item["analysis"] = analyze(fetched["history"], settings)
        else:
            item["analysis"] = {"status": "unavailable"}
        results.append(item)
        print(f"{asset['symbol']}: {item['status']}")
    for asset in assets.get("iran_local", []):
        if not asset.get("enabled"):
            results.append({
                "asset": asset["symbol"], "provider": "not_configured",
                "status": "unavailable", "market_timestamp": "—",
                "reason": asset.get("reason", "منبع پیکربندی نشده."),
                "analysis": {"status": "unavailable"}
            })
    local_now = datetime.now(ZoneInfo(settings.get("timezone", "Asia/Tehran")))
    report = render_report(results, settings, local_now)
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    out = report_dir / f"{local_now:%Y-%m-%d}.md"
    out.write_text(report, encoding="utf-8")
    print(f"Report written: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
