# Intelligence v2 — staged upgrade record

This upgrade is additive. Existing report generation, risk gates, market adapters and configuration remain intact. New modules are independently callable and do not silently change production ranking until their inputs have been validated.

## Ten upgrade stages

1. **Technical integrity:** reusable OHLC and timestamp quality gates; completed-bar discipline remains mandatory.
2. **Currency strength:** cross-sectional signed pair returns for all eight currencies with pair coverage and missing-data reporting; now calculated in the daily orchestration and displayed in the Persian report/JSON.
3. **ICT/SMC foundation:** confirmed swing points, BOS/CHoCH and three-candle fair-value gaps. Pivots are timestamped only when confirmed to avoid repainting; hourly annotations are attached to opportunity candidates.
4. **Macro surprise:** actual-versus-consensus calculations and standardized surprise only with at least eight comparable historical releases.
5. **News intelligence baseline:** transparent headline lexicon, local negation handling and exact-title deduplication. Headline labels are attached to collected RSS records and shown in the report. This is not a semantic model and must not be treated as currency impact.
6. **Expert validation:** preserve existing verified-trade ledger as the sole performance basis; future integration must use sample-size gates, expectancy, profit factor and drawdown. Social popularity is excluded.
7. **Walk-forward evaluation:** deterministic evaluator for timestamped signals and forward returns; production use still requires transaction costs, non-overlap rules and untouched out-of-sample periods.
8. **Consensus integration:** keep technical, macro, news, positioning and expert evidence separate; missing evidence remains null and conflicts are explicit. Do not blend until source timestamps and provenance are present.
9. **Reporting and automation:** add a CI quality gate (compile + unit tests); existing daily reporting is not replaced by this test workflow.
10. **Release validation:** merge only after CI passes, full repository regression tests pass, source licenses/limits are reviewed, and paper-trading results are independently reproduced.

## Important limitations

- No new live broker feed, paid API, AI inference provider or social scraping is enabled by this patch.
- The existing Yahoo-based FX pricing limitation remains until an independently licensed provider adapter and symbol mapping are configured.
- No live order execution is introduced. Existing research/paper-only risk policy remains authoritative.
- New analytics are not yet wired into the production ranking score. This is intentional: integration without verified, timestamped inputs would create false precision.
- The headline scorer is a transparent baseline, not NLP/LLM semantic understanding.
- The walk-forward evaluator is a building block, not a complete portfolio backtester.

## Local verification

```bash
python -m pip install -r requirements.txt
python -m compileall -q src tests
python -m unittest discover -s tests -v
```
