"""Read-only MCP server; serves cached snapshots, never sends orders."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
mcp = FastMCP("FX Strength Research", host="127.0.0.1", port=int(os.getenv("PORT","8000")), stateless_http=True, json_response=True)

def load():
    path = ROOT / "reports/fx-strength-latest.json"
    if not path.exists():
        return {"status":"unavailable","reason":"Run python -m src.analysis.fx_strength_mtf first"}
    data = json.loads(path.read_text(encoding="utf-8"))
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(data["cutoff_utc"])).total_seconds()
    data["snapshot_age_seconds"] = age
    data["status"] = "stale" if not 0 <= age <= 900 else "recent_cached"
    return data

@mcp.tool()
def fx_strength_snapshot() -> dict:
    """Read all 8 currencies and 28 pairs across 13 horizons with freshness."""
    return load()

@mcp.tool()
def fx_pair(symbol: str) -> dict:
    """Read a single pair from the cached research snapshot."""
    data = load()
    for row in data.get("pairs",[]):
        if row["symbol"] == symbol.upper():
            return {"status":data["status"],"cutoff_utc":data["cutoff_utc"],"snapshot_age_seconds":data["snapshot_age_seconds"],"pair":row}
    return {"status":"unavailable","reason":"No matching cached pair"}

@mcp.tool()
def fx_rankings() -> dict:
    """Return research rankings; missing horizons remain unranked."""
    data = load()
    return {k:v for k,v in data.items() if k in ("status","reason","cutoff_utc","snapshot_age_seconds","coverage","pairs","method","provider")}

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT","stdio")
    if transport not in ("stdio","streamable-http"):
        raise ValueError("Unsupported transport")
    mcp.run(transport=transport)
