# MCP market-data integration

## Status

This branch contains the first executable, read-only MCP client integration:
- MCP server: [CohenD/fin-data-mcp](https://github.com/CohenD/fin-data-mcp)
- Provider used for OHLC: OKX public market data through the MCP tool `crypto_candles`
- Transport: MCP over stdio, launched with `npx --yes github:CohenD/fin-data-mcp#b4060af854e8ea4292156c675a1de9718893d5cb` (immutable commit pin)
- Runtime: Python MCP client + Node.js 20
- Activation: `KOROUSH_FIN_DATA_MCP_ENABLED=true` (enabled in the scheduled daily-analysis workflow)
- Scope: BTC and ETH cross-check candles. USD-quoted configured symbols are explicitly marked as using an OKX USDT-quoted proxy; the adapter never claims USDT is exactly USD.
- Access: no provider API key is required for the public OKX market-data endpoint. Network access and GitHub Actions runner availability are still required.

The adapter accepts only confirmed candles, validates OHLC relationships and finite positive prices, rejects malformed/unconfirmed bars, bounds the request size and timeouts, caches successful calls briefly, and preserves the existing Yahoo/Binance fallback behavior. It is read-only and has no broker, order, account, or wallet permissions.

## Important coverage limits

The MCP project exposes several different data classes, which must not be conflated:
- Frankfurter/ECB and ExchangeRate-API provide reference FX rates and daily historical rates, not intraday OHLC candles.
- World Bank provides macroeconomic/commodity reference series, not executable market candles.
- OKX provides exchange-native crypto candles, tickers, order books and derivatives metrics.
- The free/no-key inventory does not establish full 1m–monthly OHLC coverage for all 28 FX pairs, XAU/XAG, oil, USD/IRR or local Iranian prices.

Therefore this integration only adds OKX crypto candles as an independent venue cross-check. It does not replace FX, metals, oil or Iranian local-market feeds, and no missing candle series is synthesized from reference rates.

## Twelve Data candidate

Official server: [twelvedata/mcp](https://github.com/twelvedata/mcp), hosted endpoint `https://mcp.twelvedata.com/mcp`.

It advertises historical/real-time prices and OHLC time series across forex, metals/commodities, crypto and other instruments. However, a Twelve Data account and plan entitlement are required. The hosted MCP uses interactive OAuth; that user-bound flow is not silently assumed to work as a headless GitHub Actions credential. The self-hosted mode requires `TWELVE_DATA_API_KEY`. Add it only as a repository/deployment secret after confirming the free plan's symbol, interval, request-credit and redistribution limits. Never put the key in source code, a manifest, logs, or chat.

## Central AI compatibility

The central repository's current `data_source` registry is a metadata/discovery contract for HTTPS endpoints implementing `koroush-market-data-v1` / `market.ohlc.v1`. It does not launch stdio MCP processes or execute arbitrary manifest code. Consequently, this local MCP client is intentionally not advertised as a central registry HTTP endpoint. A future central registration requires a reviewed, authenticated MCP-to-OHLC gateway with:
1. a fixed provider/tool allowlist (no arbitrary tool names or command arguments);
2. tenant/repository authorization and secret isolation;
3. explicit symbol, timeframe and quote-currency metadata;
4. completed-candle and freshness validation;
5. rate-limit, provenance, cost and terms metadata;
6. integration tests and a successful authenticated end-to-end health check.

Until such a gateway exists and is deployed, the Forex repository uses its local MCP client for the scheduled job while the central registry remains unchanged. This is deliberate: registering a stdio MCP URL as an HTTPS OHLC endpoint would be a false integration.

## Validation

Unit tests cover OKX candle normalization, rejection of unconfirmed/invalid candles, and the disabled-by-default adapter behavior. The daily workflow enables the adapter. Live verification still depends on a successful GitHub Actions runner and a live OKX response; a committed adapter is not evidence that the scheduled run has already succeeded.
