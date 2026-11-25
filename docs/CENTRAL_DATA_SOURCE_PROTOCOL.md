# KOROUSH Central dynamic market-data sources

## Purpose

The Forex engine can discover centrally registered market-data providers at runtime. A new provider that follows this protocol can be added in KOROUSH CENTRAL AI without adding a provider-specific adapter to this repository. The Forex engine continues to use its existing local providers if central discovery is unavailable.

## Discovery and authorization

The client requests:

`GET /api/extensions?repository=negahdarfar/daily-forex-analyze-&kind=data_source`

Headers:
- `X-Tenant-Key`: repository-scoped tenant key, stored only in GitHub Actions secrets
- The key must include `registry:read` in addition to the existing research scopes

Only administrator-registered, active manifests with all of the following are eligible:
- `kind=data_source`
- `protocol=koroush-market-data-v1`
- `capabilities` contains `market.ohlc.v1`
- `domains` contains `forex` or `general`
- The exact repository is allowed by the manifest, or the manifest is explicitly global
- HTTPS endpoint on the default port, no embedded credentials, and no local/private destination
- Explicit admin attestation of zero cost: `pricing.cost_usd=0`, `pricing.zero_cost_attested_by_admin=true`, `pricing.source_reviewed_by_admin=true`, and an HTTPS `pricing.terms_url`

The registry response is cached for five minutes. Up to five eligible providers are checked. The client never forwards the tenant key to a provider endpoint and never downloads or executes provider code. Redirects are disabled for provider calls.

## Provider request

The provider must accept a public, unauthenticated HTTPS GET request with:
- `symbol`: exact canonical instrument symbol from `config/markets.json`
- `interval`: one of `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`
- `limit`: requested candle count, capped at 1000

This first protocol version intentionally supports public no-key sources only. No provider-specific API key or paid service is allowed.

## Provider response

Return a JSON object with exact `symbol`, exact `interval`, and a `candles` array. Every candle must contain timezone-aware UTC `open_time` and `close_time`, plus positive numeric `open`, `high`, `low`, and `close`; `volume` is optional.

Example:

```json
{
  "symbol": "EURUSD",
  "interval": "1h",
  "candles": [
    {
      "open_time": "2026-11-25T02:00:00Z",
      "close_time": "2026-11-25T03:00:00Z",
      "open": 1.151,
      "high": 1.153,
      "low": 1.149,
      "close": 1.152,
      "volume": null
    }
  ]
}
```

The client rejects wrong symbols/intervals, timezone-naive timestamps, future or unfinished candles, incorrect interval duration, invalid OHLC geometry, non-positive prices, and empty responses.

## Source selection and fallback

- Existing Yahoo Finance data remains the baseline source.
- Public Binance data remains an additional source for the already-supported crypto instruments.
- Centrally registered sources are checked using the same symbol and interval.
- The freshest valid completed-bar timestamp wins; a provider with newer but invalid data is excluded.
- A central registry or provider outage does not stop the daily report; local providers remain available.
- Provider ID, version, trust label, source timestamp, checked providers and selection reason are retained in the returned market-data record.

## Important limitations

The central extension registry is metadata-only; it does not proxy market data or verify a provider's claims. The admin's zero-cost attestation is an onboarding control, not an independent legal or pricing audit. Data quality, licensing, symbol identity, feed delay, historical depth and reliability still require provider review and ongoing monitoring. A provider is not a broker execution quote merely because it implements this OHLC contract.

The Forex repository requires a tenant key with `registry:read`. Existing research integration keys without this scope can submit research but cannot discover data-source manifests. No tenant key is stored in this repository's source code.
