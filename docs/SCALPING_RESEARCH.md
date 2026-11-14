# AI-Trader Scalping Research: Separate Spot and Futures

## Decision
Spot and USD-M Futures must use separate strategies. Do not route both markets through the old shared Adaptive Trend v2 rules.

## Evidence reviewed
- Pindza (2026), *Microstructure alpha: hierarchical learning and cross-asset transfer in cryptocurrency markets*, Frontiers in Blockchain 9:1811716, DOI 10.3389/fbloc.2026.1811716. Uses 3.4M+ Binance minute bars across spot and perpetuals. Range-based spread proxies and realized volatility were robust features, but short-horizon forecasts were weak; the flexible LightGBM model overfit under purged validation, and tested 5-minute strategies had deeply negative net Sharpe after VIP-0 fees. It also found poor cross-coin model transfer and stronger same-coin spot/futures transfer.
- Wen, Bouri, Xu & Zhao (2022), *Intraday return predictability in the cryptocurrency markets: Momentum, reversal, or both*, North American Journal of Economics and Finance 62, 101733, DOI 10.1016/j.najef.2022.101733. Finds both intraday momentum and reversal, conditional on jumps, liquidity and market conditions.
- Shanaev, Vasenin & Stepanov (2023), *Turn-of-the-candle effect in bitcoin returns*, Heliyon 9(3), e14236, DOI 10.1016/j.heliyon.2023.e14236. Reports a 15-minute candle-boundary effect in its historical sample; treat as a hypothesis to test, not a permanent market law.
- Pinto (2025), *High-frequency dynamics of Bitcoin futures: An examination of market microstructure*, Borsa Istanbul Review 25(6), 1378–1390, DOI 10.1016/j.bir.2025.07.016. Studies Binance BTC/ETH perpetual trade data at 1m through hourly aggregations.
- Binance published regular-user spot fees are 0.10% maker/taker (with applicable BNB discount shown separately). The standard USD-M futures fee schedule has historically listed 0.02% maker / 0.05% taker; current account-specific rates must be obtained from Binance, not hardcoded as a user's actual rate.

## Futures candidate: futures_momentum_range_scalper_v1
- 15m context plus 1h directional guard; 5m signal; 1m next-bar execution and stop/target monitoring.
- Trend playbook: EMA pullback/reclaim and short-window momentum breakout, both LONG and SHORT.
- Range playbook: fade extreme Bollinger/RSI excursions only after a reversal candle when 15m ADX is low.
- 1.9R gross target, ATR-based stop, cost hurdle, one position per symbol, 24-minute time stop, cost-adjusted break-even protection after +0.9R.
- Funding is included from Binance historical funding events; 1m close is only a mark-price proxy.

## Spot candidate: spot_long_scalper_v1
- Long only; no synthetic shorting.
- 4h trend guard, 1h/15m bullish context, 5m pullback/reclaim or breakout; separate low-ADX oversold bounce.
- Higher 2.4R gross target to offset the higher spot fee burden; 36-minute time stop.
- Reject setups whose expected target does not clear the estimated round-trip cost hurdle.

## Backtest design and caveats
- Historical Binance 1m execution bars, closed 5m/15m/1h signals (Spot also uses 4h context), enter at next 1m open.
- Stop is assumed to execute before target when both are touched in the same 1m candle.
- Fees use conservative regular-user taker assumptions: 10 bps/side Spot and 5 bps/side Futures. The repository's dynamic spread/slippage remains an OHLCV proxy, not historical order-book replay.
- Futures funding is included. No historical queue position, maker fill probability, latency, or actual bid/ask order-book replay is available in the candle-only test.
- Each symbol and market is tested as an independent account. Results are not a combined portfolio.
- A higher trade count is not an objective by itself. Evaluate net expectancy after costs, profit factor, drawdown, trade count per 30 days, average holding time, and setup/rejection diagnostics together.

## Acceptance gates before adoption
1. All unit tests and 8-symbol backtests complete.
2. Compare per-symbol Spot and Futures independently; do not pool them to hide losers.
3. Report total trades and trades per 30 days, net PnL, PF, win rate, max drawdown, fees, estimated spread/slippage, and funding.
4. Use chronological development/validation/test partitions. Keep the final holdout sealed until parameters are fixed; use purged/embargoed validation around overlapping 5m labels.
5. Test parameter stability and fee/slippage stress (base, +25%, +50%, and adverse fills). Reject a configuration that only works at one narrow parameter point.
6. Calibrate thresholds per coin only on training/validation data; do not assume a strategy fitted on BTC transfers to altcoins.
7. Keep this research-only until paperless DEMO validation and explicit approval. No LIVE activation is part of this work.
