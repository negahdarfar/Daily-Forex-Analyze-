# Intelligence v2 — staged upgrade record

This upgrade is additive and isolated on `upgrade/intelligence-v2`. The `main` branch is not modified. The branch is intended for research and paper-trading analysis only.

## Ten upgrade stages

1. **Data integrity:** OHLC validation, timestamp freshness checks, completed-bar discipline and explicit stale/unavailable states.
2. **Currency strength:** cross-sectional signed pair returns for eight currencies, pair-coverage reporting, stale-pair exclusion, daily report output, and direct integration as a weighted input to the 28-pair FX shortlist.
3. **ICT/SMC structure:** confirmed swing pivots, BOS/CHoCH and three-candle FVG. Swing pivots are timestamped only at confirmation. Recent directional BOS/CHoCH and FVG confluence now contribute a separate, configurable FX ranking component.
4. **Macro intelligence:** policy-rate carry and 90-day change remain a clearly labeled proxy. Actual-versus-consensus surprise calculations are available as a module, but a complete timestamped multi-currency consensus-release feed is not connected.
5. **News intelligence:** transparent headline lexicon, local negation and deduplication; headline labels are attached to RSS records. This is not semantic NLP and is not treated as verified currency impact.
6. **Expert performance:** unverified social claims are not promoted to verified trade performance. A source-backed trade ledger, minimum sample threshold and independently reproducible expectancy/profit-factor/drawdown record remain outstanding.
7. **Walk-forward evaluation:** timestamp-safe next-bar outcomes now support configurable spread, commission, slippage, holding windows and overlap blocking. This is still not a broker fill simulator or full portfolio backtester; stop/target intrabar ordering, financing, gaps, contract sizing and strict out-of-sample splits remain necessary.
8. **Evidence consensus:** technical, policy-rate and relative currency-strength evidence are combined only when present, fresh and verified. Coverage is explicit; the consensus is a diagnostic/tie-breaker, never a probability. RSS and unverified expert claims are not silently counted as verified.
9. **Reporting and automation:** the daily JSON/report includes currency-strength output; a GitHub Actions quality workflow runs compile and unit-test commands when GitHub Actions executes it. The latest branch commit currently has no reported workflow run or status check, so CI is not yet verified.
10. **Release validation:** still pending. Do not merge until CI, regression tests, source/license review and reproducible paper-trading validation pass.

## Current technical ranking design

- FX shortlist weights are configurable and total 100 points: technical 16, MTF 12, policy-rate proxy 17, COT 13, news 8, expert 8, freshness 5, calendar 5, relative currency strength 8, and recent structure confluence 8.
- Missing components remain null and are excluded from the available-weight denominator. Coverage and missing-evidence fields remain visible.
- The consensus diagnostic requires fresh verified evidence and reports coverage/conflict separately. It is not a win probability.
- High-impact event coverage remains USD-only. The other seven currency calendars are not represented as clear.
- Existing execution gates remain conservative: missing instrument-specific round-trip costs block active opportunities; minimum net R/R remains configured; live orders remain disabled.

## Known limitations that must not be hidden

- FX prices still rely primarily on Yahoo Finance indicative data. A second independently licensed FX feed with validated symbol mapping is not connected.
- No complete calendar and market-consensus forecast feed exists for all eight currencies.
- The expert performance system is not yet a verified trade-record leaderboard.
- The walk-forward evaluator is an evaluation building block, not a complete portfolio backtester.
- The simple news sentiment score is not a semantic model or causal market-impact model.
- No live broker execution, automatic order placement or paid inference service is introduced.

## Local verification commands

```bash
python -m pip install -r requirements.txt
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

A green workflow and independently reproduced test output are required before describing this branch as validated or production-ready.
