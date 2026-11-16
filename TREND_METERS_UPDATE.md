# Dashboard trend meters

Dashboard now shows red / grey / green semicircular meters for every returned index, following the uploaded reference. The needle uses the existing signed rule score: negative bearish, zero centre, positive bullish. Labels retain the backend Uptrend / Downtrend / Sideways classification. The score is not a calibrated probability, so no percentage claim is shown. Missing data has no needle. Historical status, IST candle timestamps, and existing reasons/warnings remain visible. No backend scoring or trading logic changed. Light/dark themes and narrow screens are supported.

## Install

1. Stop the application.
2. Download this branch ZIP and extract into a separate folder.
3. Run UPDATE_TREND_METERS.bat. It backs up files, updates the existing H-drive installation, runs existing tests and builds the frontend.
4. After validation passes, run START_INSIGHTS.bat from the existing installation.
5. Press Ctrl+F5 and open Dashboard. Check both light and dark themes. Without index data, Awaiting data is expected.

Changed UI files: web/src/trend_meter.js, web/src/main.js and web/src/styles.css. This cumulative ZIP includes previous features including Event Calendar and notifications.
