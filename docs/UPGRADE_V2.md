# Intelligence v2 — implementation and validation record

This upgrade is isolated on `upgrade/intelligence-v2`; `main` remains unchanged. It is a research/paper-trading system, not a live execution system.

## Ten intelligence stages

1. **Data integrity:** OHLC validation, timestamp freshness checks, completed-bar discipline and explicit stale/unavailable states.
2. **Currency strength:** cross-sectional signed pair returns for eight currencies, pair-coverage reporting, stale-pair exclusion, daily report output and a weighted input to the 28-pair FX shortlist.
3. **ICT/SMC structure:** confirmed swing pivots, BOS/CHoCH and three-candle FVG. Swing pivots are timestamped only at confirmation. Recent directional BOS/CHoCH and FVG confluence contribute a configurable ranking component.
4. **Macro intelligence:** BIS policy-rate carry and 90-day change remain a labeled proxy. The new global calendar preserves provider consensus, previous and actual values; numeric actual-minus-consensus is descriptive only and is not mapped to bullish/bearish without event-specific economics.
5. **News intelligence:** transparent headline lexicon, local negation and deduplication; not semantic NLP or a causal impact model.
6. **Expert performance:** new auditable ledger validator joins named registered analysts to independently reviewed closed trades. Self-verification is rejected. At least 30 closed trades, positive expectancy, profit factor above 1 and at least two verified analyst publishers are required for a directional expert score. No real analyst ledger records are included by default.
7. **Backtesting:** new OHLC simulator enters at the next bar open, sizes at 1% of current equity by default, applies explicit spread/commission/slippage, blocks overlapping trades per symbol and assumes stop-first when stop and target occur in the same candle. This is conservative but not a broker/tick simulator.
8. **Evidence consensus:** technical, policy-rate and relative currency-strength evidence are combined only when present, fresh and verified. Coverage is explicit; consensus is a diagnostic/tie-breaker, never a probability.
9. **Reporting and reproducibility:** report now records a run ID, configuration fingerprints, source timestamps/statuses, report and JSON hashes, ECB checks, backtest state and forward paper-trading state. A run manifest is written alongside Markdown and JSON outputs.
10. **Release validation:** still pending. The latest GitHub Actions runs failed before runner assignment (runner_id=0, empty runner_name and no steps). No compile or unit-test step has run; do not merge or call the branch production-ready.

## Five follow-up items: implementation state

### 1. Independent price validation
- Connected official ECB daily reference rates as an independent benchmark for cross-rate checks against Yahoo daily closes.
- Cross rates are derived from currencies-per-EUR observations and reported with percentage discrepancy.
- ECB reference rates are not intraday prices, not executable quotes, and do not replace Yahoo. A second independently licensed intraday broker/feed for all 28 pairs is still not connected. Do not describe ECB as a full second real-time price provider.

### 2. Multi-currency event calendar and consensus
- Connected the free no-key ShowMyTrades calendar for USD, EUR, GBP, JPY, CHF, CAD, AUD and NZD; CNY may appear in the provider but is not in the FX-eight ranking universe.
- Retains event timestamp, currency, impact, forecast, previous, actual, status and confidence; XOOMAR supplements US agency schedules.
- Pair calendar risk now checks both currencies and uses high/medium impact blackout windows.
- Numeric surprise is displayed only when actual and forecast can be parsed to comparable scalar units. No generic directional surprise score is invented. Provider completeness and event classifications remain external-source limitations.

### 3. Verified analyst performance
- Added `src/experts/verified_ledger.py` and `data/verified_trades.example.json`.
- Each ledger entry requires a closed trade, analyst identity, source URL, verifier distinct from the analyst, verification timestamp and evidence reference. Realized R is recomputed from entry/stop/exit and fees; supplied realized-R claims are not trusted.
- The actual `data/verified_trades.json` is intentionally absent. Therefore expert-performance ranking remains unavailable until genuine evidence is reviewed and entered. Example data is a schema illustration only and must not be treated as real trades.

### 4. Cost-aware OHLC backtest
- Added `src/analysis/ohlc_backtest.py`, `config/backtest.json` and `data/backtest_signals.example.json`.
- Default account equity is USD 10,000 and default risk is 1% per trade. All three cost assumptions (spread, commission, slippage) must be explicitly configured; null blocks the backtest.
- Actual backtest remains pending until timestamped historical signal records are supplied in `data/backtest_signals.json` and instrument-appropriate costs are entered. This prevents fabricated backtest results.
- Still missing: bid/ask tick fills, swap/financing, margin/lot constraints, broker-specific contract sizing, robust walk-forward train/test splits and full portfolio cross-symbol capital allocation.

### 5. Reproducible report and forward paper trading
- Added run IDs, config SHA-256 fingerprints, source status/timestamps, output hashes and `*-run-manifest.json`.
- Report now explicitly distinguishes historical OHLC simulation from forward paper trading.
- Forward paper validation has not yet run. The repository has no broker/demo execution connection, no durable forward trade lifecycle and no verified fill log. Live orders remain disabled.

## FX shortlist weights

Configurable weights total 100 points: technical 16, MTF 12, policy-rate proxy 17, COT 13, news 8, expert 8, freshness 5, calendar 5, relative currency strength 8, and recent market structure 8.

Missing components remain null and are excluded from the available-weight denominator. Coverage and missing-evidence fields remain visible. A score is not a probability or guarantee of profit.

## GitHub Actions runner issue

Observed failed jobs have `runner_id=0`, empty `runner_name` and `steps=[]`. This means the job failed before any test command ran. GitHub's troubleshooting guidance recommends checking account billing/spending limits, repository/org Actions policy, hosted-runner availability and GitHub Status; if still unresolved, provide the run URL to GitHub Support. See:
- https://docs.github.com/en/actions/how-tos/troubleshoot-workflows
- https://docs.github.com/en/actions/how-tos/get-support

No workflow green status is claimed. The workflow file itself still contains compile and unit-test steps.

## Local validation commands

```bash
python -m pip install -r requirements.txt
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

Do not merge until the workflow actually receives a runner and passes, local regression tests pass, data-source terms are reviewed, and a forward paper-trading period has been independently checked.


## Dynamic KOROUSH Central data-source integration

The Forex market-data adapter now discovers administrator-registered `kind=data_source` manifests from the central extension registry using the exact repository identity and the `registry:read` tenant scope. It supports the versioned public OHLC protocol documented in `docs/CENTRAL_DATA_SOURCE_PROTOCOL.md`.

- Eligible sources must be active, use `koroush-market-data-v1` / `market.ohlc.v1`, be scoped to Forex/general, declare an administrator-attested USD 0.00 cost and HTTPS terms URL, and expose a safe HTTPS endpoint.
- Registry discovery is cached for five minutes. At most five sources are queried; redirects are disabled and the tenant key is never sent to provider endpoints.
- The provider response is validated for exact symbol/interval, UTC timestamps, completed bars, interval duration and OHLC geometry.
- The freshest valid completed bar is compared with existing Yahoo and (where applicable) Binance results. Invalid or stale central sources do not displace a valid local source.
- If central configuration, registry access or a provider is unavailable, the existing local provider path continues.

This is a metadata-driven adapter, not arbitrary plugin execution. Only public no-key feeds are supported in v1. Admin registration and the zero-cost attestation still require human review; the central registry does not independently certify licensing, source accuracy or uptime. The Forex tenant key needs `registry:read` in addition to the research scopes. No production central source is claimed until a real manifest is registered and a successful data fetch is observed.
