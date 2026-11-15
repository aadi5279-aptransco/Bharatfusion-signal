# Additional QGLP research in Multibagger

This update implements the uploaded `multibagger_screen.py` as an additional panel. The existing technical Multibagger research, its fundamentals/surveillance checks and all trading strategies remain unchanged. No Dhan calls or five-minute scans are added. The new screen works from user-imported fundamentals; it does not manufacture missing financial data or scrape a subscription export.

## Install

1. Stop the application/backend.
2. Download the ZIP for `feature/qglp-multibagger-20261115` and extract it to a separate folder, outside the installed application.
3. Double-click `UPDATE_QGLP_MULTIBAGGER.bat`. Its default target is `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`. For another target, run `UPDATE_QGLP_MULTIBAGGER.bat "YOUR_PROJECT_PATH"` from CMD inside the extracted folder.
4. The cumulative updater backs up replaced source files, preserves credentials/database, runs the tests and builds the frontend. It includes the earlier order-flow and European dashboard code. Stop if validation fails.
5. Run `START_INSIGHTS.bat` in the existing installation, refresh the browser with Ctrl+F5 and open **Multibagger**.

## Use the new panel

1. Click **Download CSV column template** in the QGLP panel.
2. Export your fundamental data, or populate the template from attributed financial reports. For Excel, use **Save As > CSV UTF-8**. Direct XLS/XLSX upload is not supported in this first integration.
3. Include every required column below. Extra unrelated columns are ignored. Numeric blanks, dashes, invalid values and missing pledge figures remain unverified, never zero. Missing required headers reject the import. Duplicate identifiers or duplicate mapped columns reject the import to avoid distorted rankings.
4. Enter the export date, the latest financial period end used by ALL rows, and a source description. Split different reporting-period datasets into separate imports. Export date must be within 180 days; financial period end within 210 days. Dates cannot be in the future or period end after export date.
5. Click **Import and rank**. This replaces only the QGLP dataset, saves it locally and survives restart. Re-import when fundamentals change. Staleness is re-evaluated whenever the panel is loaded.
6. Filter qualified/rejected/unverified stocks and expand **View checks and score** for each company. Results are paginated, with every check and weighted score component available. The original technical research is below the new panel and has its own eligibility requirements.

Required headers (the script's internal names also work):

| Header | Meaning / unit |
|---|---|
| Name | Company name |
| Market Capitalization | ₹ crore |
| Return on capital employed | Percentage points |
| Return on equity | Percentage points |
| Sales growth 3Years | Three-year sales CAGR, percentage points |
| Profit growth 3Years | Three-year profit CAGR, percentage points |
| Debt to equity | Ratio |
| Price to Earning | P/E ratio |
| Promoter holding | Percentage points |
| Pledged percentage | Percentage points, on a consistent reported basis |
| Operating cash flow 3years | Cumulative CFO for the same three financial years, ₹ crore |
| Net profit 3years | Cumulative PAT for those three years, ₹ crore |

Optional: **Symbol**, **Sector**. Enter percentages as `15`, not `0.15`. Thousands separators are supported when properly CSV-quoted. Parentheses represent negative numbers. Do not substitute a single year's CFO/profit for three-year totals or mix consolidated and standalone figures. An export date does not independently verify financial accuracy.

## Rules and improvements

Preserves the uploaded hard filters: market cap ₹500–15,000 crore, ROCE ≥15%, sales and profit growth ≥15%, debt/equity 0–0.7, pledge 0–10%, promoter holding 40–100%, cash conversion ≥0.7. Cash conversion requires positive cumulative three-year profit. Positive P/E is required for meaningful PEG; PEG = P/E divided by the growth percentage number. ROE and all other scoring inputs must be present and finite.

Unlike the uploaded script, absent columns cannot silently bypass filters, missing pledging is not assumed zero, and missing cash flow cannot disable cash-quality screening. Negative/zero profit cannot create a misleading positive cash conversion. Known banking/finance/insurance/NBFC sectors are flagged unsupported for this industrial-company model. If Sector is absent, a suitability warning remains and must be reviewed manually.

Ranking retains the uploaded weights: ROCE 20%, ROE 10%, sales growth 15%, profit growth 15%, cash conversion 15%, debt/equity 10%, PEG 15%. Higher is better except debt/equity and PEG. Weighted percentile positions are normalized to 0–100 among fully qualified rows; tied values receive average positions. A single qualifying company scores 50, not 100. Tied final scores share rank. Changing the imported universe changes relative scores. These are not probabilities, predicted returns, investment recommendations or absolute quality grades.

The output shows qualified, rejected, unverified, unsupported-sector and stale statuses, with checks and reasons. QGLP qualification does not certify exchange surveillance, liquidity, long-term competitive advantage or future growth. Longevity and growth consistency still require review of financial history and business evidence. No entry, SL or targets are inferred from financial ratios; the existing technical research remains separate.

## Files and validation

New code: `insights/qglp.py`, `web/src/qglp.js`, `insights/tests/test_qglp.py`. Integration touches service initialization, isolated local API routes and Multibagger rendering only. Imported data is stored at `BHARATSIGNAL_INSIGHTS_HOME/qglp_import.json`, default `%USERPROFILE%\.bharatsignal-insights\qglp_import.json`. Invalid imports preserve the previous saved dataset. Local-only, same-origin upload protections and 2 MB / 10,000 row limits apply.

Tests cover missing inputs, zero/missing pledging, invalid values, filter failures, negative profit, ranking direction/ties/singletons, date validity, unsupported sectors, persistence, API imports and remote rejection. Automated tests do not establish investment performance.
