# Analyse: built-in SMC expert assessment and ATM premium scenarios

Selecting a mapped stock/index runs the existing Analyse workflow and an additional explainable SMC expert system. This is rule-based AI (an expert system), not trained machine learning. No labelled training dataset, fitted model, calibrated probability, backtested edge or superior performance is claimed. “All SMC” has no single implementable definition; this version explicitly covers the concepts below, rather than claiming every interpretation.

## Evidence
- Completed 5-minute candles; pivots need two completed bars on each side. The latest trigger candle cannot create its own pivot reference.
- BOS: latest close crosses the last confirmed swing high/low.
- CHoCH: such a break opposes the previously observed higher-high/higher-low or lower-high/lower-low swing sequence. This is a disclosed operational definition.
- Liquidity sweep: wick crosses a confirmed swing reference and closes back across it.
- Displacement: directional candle body >=0.8 ATR14.
- Three-candle FVG zones in the preceding 20 bars; close through the far edge invalidates a zone. A latest-candle overlap plus close beyond the near edge counts as a retest/rejection.
- Order-block proxy: last opposite candle within six preceding bars before BOS plus displacement. Retest is NOT assumed and no institutional identity is inferred.
- Premium/discount: close versus midpoint of the latest confirmed swing range; contextual only, not an option premium price.
- 5m/15m/60m EMA9/21 trend agreement; only completed, recent, finite, valid data. At least 35 bars on each timeframe. Stocks additionally require RVOL >=1.5; cash indices do not require reported volume.

Confluence score: MTF agreement 30, BOS 25, sweep 15, displacement 15, active FVG retest 15. Minimum 65 plus a fresh BOS or sweep. This is rule confluence, not winning probability. Pattern evidence is shown for CE and PE, even when no recommendation qualifies.

## Option-chain and premium checks
The model requires a positive available PCR: >=0.85 CE or <=1.15 PE. PCR is a positioning proxy, not proof of buying or selling. Chain spot must agree with completed cash price within max(2 ATR, 0.5% of spot). The independently selected direction must agree with an explicitly requested CE/PE side. Verified market session required.

Use the nearest listed ATM strike and chosen expiry from Dhan. Require a mapped security ID, positive contract volume/OI and valid bid/ask spread <=2%. Fetch that exact option's 5-minute premium candles (OPTIDX/OPTSTK and NSE_FNO/BSE_FNO mapping). No cash-price substitution for option levels.

With at least 20 recent premium candles, hypothetical entry is best ask. SL is the lower of the latest three premium lows and entry minus premium ATR14. Require risk 3–35% of premium, positive ordered rounded levels and ask within two ATR of the latest premium close. T1=entry+1.5R; T2=entry+2.5R. These limits are research defaults, not an optimized risk model. Both CE and PE are option-buying scenarios, so targets exceed premium entry.

Missing premium history or any blocker means WATCH with no new entry/SL/targets. There is no fallback to the old fixed 20% premium stop. Existing legacy API fields remain for compatibility, but the Analyse ATM panel uses `smc_atm` and displays `smc_model` evidence. Other tabs' strategies are unchanged.

Chain receipt time does not establish exchange quote freshness. All resulting levels remain hypothetical; no orders are placed. Historical/after-close analysis does not produce a new live model entry. Greeks/IV and OI remain available through the existing chain diagnostics; this version does not infer historical IV percentile or executed order flow from them.

Dhan data references checked: https://dhanhq.co/docs/v2/historical-data/ and https://dhanhq.co/docs/DhanHQ-py/api/_option_chain/

## Install
1. Use Logout / Exit to stop the app (or Ctrl+C if your installed version predates that button).
2. Extract the update ZIP separately and run UPDATE_ANALYSE_SMC.bat. Default target: H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights.
3. Wait for validation to succeed; start your existing START_INSIGHTS.bat and press Ctrl+F5.
4. Open Analyse, choose/type a mapped stock/index and analyse. Review “SMC expert model · ATM option research” and the evidence/blocker panel. Select an available expiry if needed.
5. During a verified market session, qualifying data produces ATM contract, premium entry, T1/T2, SL and reasons. Otherwise the strike may still be visible with a WATCH reason and blank levels. Non-optionable/unmapped instruments cannot get invented contracts.

Test: .venv\Scripts\python.exe -m unittest insights.tests.test_smc_expert -v

Core files: insights/smc_expert.py, insights/analyse_workflow.py, web/src/main.js. Tests use synthetic fixtures and do not establish live profitability. A trained statistical model would require a separate point-in-time historical dataset, outcome labels, transaction costs, temporal holdout and walk-forward calibration; none is silently trained on the selected stock's current candles.
