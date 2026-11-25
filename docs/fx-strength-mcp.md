# FX Strength / MCP (research MVP)

The independent scanner uses the existing Yahoo Finance adapter dependency, with 5-minute and hourly history. No key is required for this unofficial feed, which can fail, be delayed or be subject to provider restrictions. Use only where permitted. The 13 horizons are rolling elapsed durations, not calendar candles: W1=7 days, MN=30 days. This is not the proprietary Currency Strength Zone formula.

All 28 pairs must have observations with a common endpoint per horizon; unavailable cells are null. The short-horizon endpoint is the last completed 5-minute bar. No order execution. Equal horizon weights and min-max scores are research design choices, not win probabilities. Net R/R is null because this independent scanner does not have execution costs or a validated entry setup.

## Run
```sh
python -m pip install -r requirements-mcp.txt
python -m unittest discover -s tests -p test_fx_strength_mtf.py
python -m src.analysis.fx_strength_mtf
python -m src.fx_mcp_server
```

Snapshot: reports/fx-strength-latest.json. MCP tools: fx_strength_snapshot, fx_pair, fx_rankings. By default the server uses stdio. For local HTTP testing, set MCP_TRANSPORT=streamable-http; the server listens on loopback port 8000 (/mcp). This is deliberately not a publicly exposed authenticated endpoint. To connect ChatGPT remotely, deploy behind an authenticated HTTPS gateway supported by the client; do not expose the unauthenticated local endpoint. GitHub stores code but does not host a persistent MCP process.

Dukascopy and official TradingView are not integrated yet. A second provider, OHLC setup scoring and real-data validation are follow-up work.
