# Index Options scheduling and red-bar visibility fix

## Gaps found in the code

The prior scheduler ran Index Options only when the sampled clock minute was exactly divisible by five. A delayed loop could skip that opportunity, especially after broad stock discovery and multiple stock scans. Failed scans were marked done before success. Opening and Fibonacci checks independently downloaded the same five-minute history. Session slicing assumed the frame already used IST. The UI did not prominently expose the difference between an underlying direction watch and a legacy premium scenario, or all waiting reasons.

This audit does not establish the exact reason on your Windows installation without its runtime diagnostics. It fixes reproducible scheduling/data-handling gaps; data entitlement, mapping and a genuinely unconfirmed setup can still explain no signal.

## Changes

- Runs the small mapped-index scan before broad stock scans, starting 09:20 IST. Once-per-five-minute buckets catch a delayed tick such as 09:31 or 09:36; exact minute equality is no longer required.
- A thrown scan failure remains retryable in the same bucket. Broker locks and verified market-session/calendar requirements remain enforced. Long active broker jobs can still delay the next scheduler iteration; this is not a hard real-time deadline.
- Shares one completed, IST-normalized five-minute frame between opening and Fibonacci checks per index. One index history failure does not hide other indices.
- Shows mapping warnings for NIFTY, BANKNIFTY and SENSEX, correct mapped-index scan counts and an independent-index scan label rather than the stock-liquidity label.
- Normalizes UTC candles to IST before session filtering. Rejects invalid/nonfinite prices, negative volume and stale bars. Latest candle end must be within ten minutes of assessment, allowing normal provider boundary delays. A fresh fetch does not turn old candles into current signals.
- Adds a top-of-tab readiness panel with underlying entries/T1/T2/SL for confirmed opening directions, a manual **Refresh index strategies** button and visible per-index issues. The existing strategy table now includes each waiting/rejection reason and the latest two post-reference closes.

- Fixes watch notifications that carried an `underlying` name rather than a `symbol`; ready red-bar/Fibonacci directions can now reach the notification inbox as explicitly labelled watches.

## When a signal is possible

The first 09:15–09:20 candle is the range reference. Its first two subsequent completed candles end at 09:25 and 09:30, so first-range confirmation cannot occur before 09:30.

For red-bar theory, the first strictly red five-minute candle AFTER the first candle is the reference. If it starts at 09:20, it closes at 09:25; two later closes are available only at 09:35. If the first red bar appears later, confirmation is later. No red candle, no two-close sustain, a close within the 0.44–0.56 band, missing bars or unsuitable risk can correctly produce WAITING/NO_TRADE/WATCH.

The existing red-bar orientation remains HIGH=0 and LOW=1: 0.44 is the upper boundary, 0.56 the lower boundary. Two subsequent closes above 0.44 give a CE directional watch; below 0.56 give a PE directional watch. Rules have not been weakened to force signals.

**Displayed opening/red-bar levels are underlying INDEX prices, not option premiums.** A CE/PE direction watch is not an executable option trade. Existing premium scenarios still require fresh Dashboard trend context, SMC/MTF alignment and option-chain gates; premium quote-age limitations remain explicit. Live order-flow is its separate panel and still requires its own warm-up/coverage.

## Windows installation and live check

1. Stop the application.
2. Download this branch ZIP and extract into a separate folder outside your installation.
3. Run `UPDATE_INDEX_OPTIONS_FIX.bat`. Default target: `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`.
4. Wait for backups, tests and frontend build to pass. Restart `START_INSIGHTS.bat` from the existing installation and press Ctrl+F5.
5. During a configured market session, open Index Options and inspect **Index strategy readiness**. Check mapped count, last scan time and any mapping/history issues.
6. Click **Refresh index strategies** if needed. BUSY means another Dhan scan holds the shared lock; retry after that scan. Automatic scheduling will catch up. Results poll every 20 seconds.
7. Check the opening table's trigger levels, last closes and reason. Before 09:30/09:35, waiting is expected. A later no-signal state requires reading the displayed condition; it is not automatically an error.

This cumulative update includes earlier features. No order placement is introduced. Tests validate scheduling, timezone handling, failure isolation and rule behavior; live Dhan availability and profitable execution are not guaranteed.
