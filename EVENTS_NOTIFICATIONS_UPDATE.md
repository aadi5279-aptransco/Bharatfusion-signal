# Event Calendar and notifications

Adds an Event Calendar tab and a global notification inbox. Existing strategy calculations, scan schedules, entries, targets and stops are unchanged. Separate daemon workers read cached research outputs every five seconds and refresh public feeds approximately every five minutes. No additional Dhan calls or Dhan scan locks are used.

## Install on Windows

1. Stop the application/backend.
2. Download branch `feature/events-notifications-20261115` as a ZIP. Extract it into a separate folder outside your installation.
3. Double-click `UPDATE_EVENTS_NOTIFICATIONS.bat`. Default destination: `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`. Alternatively run `UPDATE_EVENTS_NOTIFICATIONS.bat "YOUR_PROJECT_PATH"` from CMD in the extracted directory.
4. Wait for backups, source installation, tests and frontend build to pass. This is a cumulative update including the prior QGLP, European dashboard and order-flow additions. Existing credentials, settings and market database remain in place. Do not restart if validation fails.
5. Start `START_INSIGHTS.bat` from the existing installation and press Ctrl+F5 in the browser.
6. Open **Event Calendar**. Allow the first feed cycle to finish. Expand source health to see each source's last successful fetch and any errors.
7. Notifications appear globally above the tab content. Click **Enable desktop alerts** and allow the browser permission if you want Windows/browser pop-ups. In-app notifications work without that permission. Browser/Windows notification settings or Focus Assist may still suppress desktop banners.

## Free sources and calendar scope

- RBI press-release RSS: https://www.rbi.org.in/pressreleases_rss.xml
- PIB press releases: https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1
- Federal Reserve monetary-policy RSS: https://www.federalreserve.gov/feeds/press_monetary.xml
- ECB RSS: https://www.ecb.europa.eu/rss/press.html
- BBC Business: https://feeds.bbci.co.uk/news/business/rss.xml
- BBC World: https://feeds.bbci.co.uk/news/world/rss.xml
- BLS scheduled releases: https://www.bls.gov/schedule/news_release/bls.ics

No API key or paid subscription is required for these public feeds. Publisher availability is not guaranteed. Failures are isolated by source, preserve cached items and show a warning. Source attribution and original links are displayed; article bodies are not copied. BBC feeds are for this personal local reader; business/public redistribution requires checking permission. Provider terms can change.

The news section shows up to 100 recent source headlines, publication times in IST and keyword-based topic/possible-sector exposure. Topics include rates/inflation, growth/policy, energy, trade/geopolitical risk and company results. These tags do not predict direction or quantify impact; headlines can be irrelevant or incomplete. Missing dates remain unknown and cannot trigger a fresh-news notification. Publication time is not an upcoming event time. The search/date filter applies to both sections.

BLS supplies automatic upcoming economic releases (up to 120 days ahead), converted from US Eastern time with daylight saving. Cancelled events are omitted, and a successful refreshed calendar replaces the earlier schedule. Date-only and recurring entries are skipped rather than assigned invented times. This is not a complete global or Indian economic/earnings calendar. RBI MPC, Budget, FOMC meetings and company results may be added manually from an official announcement using **Add an announced event with its source**. Enter the time in IST. Manual dates are user supplied, not independently verified. Remove/re-add a manual event if changed or cancelled. No automatic company earnings coverage is claimed.

For scheduled events, the application emits one reminder when it observes an event due within the next 15 minutes. If started later within that window, it reminds then; it does not send missed reminders after the event. Automatic-calendar reminders require a successful source refresh within 24 hours and no current source error. News initial history is loaded silently. Subsequent newly detected headlines published within six hours notify when keyword-relevant, or from RBI/Fed/ECB. Repeated headlines with the same source identifier do not notify again. This is polling, not a real-time wire service.

## Research notifications across tabs

Alerts retain the module label and instrument, strategy, direction, available entry/SL/T1/T2 and reasons. Covered outputs: Intraday, F&O Stocks, Index Options, BTST and its confirmed closing layer, Swing Trades including ready opportunities and conditional guide research, ready Positional setups, eligible original Multibagger research, conditional Analyse scenarios and Index Options order-flow research.

Discovery lists, waiting/stale/blocked positional setups, Scanner filter matches, QGLP financial rankings and FII ownership changes are not silently converted into trades. They do not create executable trade alerts. A Multibagger eligibility alert is a research watch, not a price entry. Option-chain premium freshness limitations remain in the message. Opening/Fibonacci studies are underlying-price watches. Order-flow alerts explicitly say **FUTURES reference levels, NOT option premiums**. Nothing places an order.

Only a module snapshot updated within ten minutes is considered for a newly detected alert; historical daily-close research remains labelled as such. Ordinary setup alerts are deduplicated once per IST day, module, symbol, strategy, side, expiry and strike. Small price changes on repeated scans do not resend them; a same-day repeat of that same setup is intentionally suppressed. Confirmed order-flow alerts use their confirmation timestamp. Deduplication persists through backend restarts. Alert history is not a current executable signal list: always open the source tab to check present validity.

The inbox shows the latest 200 notifications and total unread count. **Mark all read** updates saved state. In-app pop-ups show up to three new recent alerts; all retained alerts remain in the inbox. Desktop bursts above three are grouped. First opening loads earlier history silently, and alerts older than two minutes are not replayed as desktop pop-ups. Browser cursor/preference persist locally. Different browsers/profiles may have separate desktop delivery state. Multiple open application windows can produce redundant desktop delivery; use one window for notifications.

The backend must stay running to fetch, detect and record. The browser must stay open for in-app/desktop delivery; browser timers may be throttled while minimized. This is not push delivery to a closed browser or a mobile device. Notifications remain saved while the browser is closed and can be reviewed on return, but old alerts are not replayed as fresh pop-ups.

## Files and checks

New files: `insights/event_center.py`, `web/src/event_center.js`, `insights/tests/test_event_center.py`. Small integration changes add service lifecycle, read-only/local API routes, the sidebar tab and global inbox. State is separate at `%USERPROFILE%\.bharatsignal-insights\event_notifications.sqlite` or your `BHARATSIGNAL_INSIGHTS_HOME`. Alerts are retained for 30 days; dated news for 14 days. Manual events have a removal control. Feed requests have timeouts and response-size limits; URLs are restricted to HTTP(S) for display and user event links are not fetched.

Automated checks cover RSS parsing, unknown/future publication dates, unsafe XML rejection, BLS winter/summer timezone conversion and cancellations, first-load suppression, persistent deduplication, source failure isolation, stale/setup guards, origin/price labels, event reminders, read state and local-only write APIs. Build and full regression tests do not establish live trading performance.
