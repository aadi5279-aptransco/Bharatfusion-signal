# Top-bar exit and removal of Event Calendar tab

The top-right Logout / Exit button stops the local BharatSignal server and background scanners after confirmation. This local app has no authenticated login session: the action exits the app rather than revoking your Dhan token. Credentials, saved watchlists and databases are retained. Other open tabs using this server become offline. The browser tab itself stays open with an exit-requested message.

Event Calendar is removed from navigation and page rendering. Trade notifications and the notification inbox remain available. Existing event/news alerts can still appear in that inbox; links to the removed Calendar tab go to Dashboard. This change does not delete saved event data.

## Windows update
1. Close the running backend once using your existing method (Ctrl+C in its CMD window). This last manual stop is necessary to replace the old launcher.
2. Extract the update ZIP into a separate folder and run UPDATE_APP_EXIT.bat.
3. The updater backs up and copies the new run_insights.py launcher, backend modules and frontend source; preserves credentials/data; runs tests and rebuilds the frontend.
4. After validation succeeds, start START_INSIGHTS.bat in your existing project and press Ctrl+F5 in your browser.
5. Check that Event Calendar is absent. Click Logout / Exit at top-right, then confirm. The server closes and background services receive their stop signal. Cancel leaves the app running.
6. To reopen, double-click START_INSIGHTS.bat. No CMD command is needed to exit after this update.

Default installation folder: H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights. Pass a different quoted project folder as the BAT argument if needed.

The exit endpoint is local-only, POST-only, same-origin, and requires a random per-process request token. It is enabled by the updated launcher; unsupported runners show an explanatory error rather than pretending to exit. The launcher closes its server socket in a finally block and signals the existing service stop routines. It does not forcibly kill unrelated Python processes.

Validation includes a real local HTTP server: fetch control token, POST exit, receive the response, observe server-thread termination and service cleanup. Other checks cover remote/cross-origin requests, missing or invalid tokens, repeated exit requests and unsupported launchers.
