"""Local Flask API. Does not expose Dhan credentials or order endpoints."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from insights.config import IST,API_BIND
from insights.service import InsightsService,DISCLAIMER


def create_app(service=None):
    from flask import Flask,request,jsonify,send_from_directory
    path=Path(__file__).resolve().parent.parent/'web'/'dist'
    app=Flask(__name__,static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=2_100_000,JSON_SORT_KEYS=False)
    service=service or InsightsService()
    app.extensions['insights_service']=service
    @app.before_request
    def limit_requests():
        # Only the CSV import needs a larger body than existing endpoints.
        if request.path!='/api/v1/market-insights/fii-holdings/import' and (request.content_length or 0)>16384:
            return jsonify(error='Request too large'),413
        if request.method=='POST' and request.path.startswith('/api/v1/market-insights/fii-holdings/'):
            if request.remote_addr not in ('127.0.0.1','::1'):
                return jsonify(error='Local requests only'),403
            origin=request.headers.get('Origin')
            if origin and origin!=request.host_url.rstrip('/'):
                return jsonify(error='Same-origin requests only'),403

    @app.get('/api/v1/market-insights/fii-holdings')
    def fii_holdings():
        result=service.fii_holdings_manager.snapshot()
        # The deal symbols define a scan universe, not verified FII activity.
        symbols=sorted({r[2] for r in service.fii_deals_manager.store.recent(15)})
        result.update(deal_symbols=symbols[:200],deal_symbol_count=len(symbols))
        return jsonify(result)

    @app.get('/api/v1/market-insights/fii-holdings/template')
    def fii_holdings_template():
        return app.response_class('Symbol,Previous pct,Current pct,Previous quarter,Current quarter\r\n',
            mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=fii_holdings_template.csv'})

    @app.post('/api/v1/market-insights/fii-holdings/refresh')
    def refresh_fii_holdings():
        payload=request.get_json(silent=True)
        if not isinstance(payload,dict):return jsonify(error='Expected JSON with symbols'),400
        try:result=service.fii_holdings_manager.start(payload.get('symbols'))
        except ValueError as exc:return jsonify(error=str(exc)),400
        status=result['status']
        return jsonify(result),202 if status=='STARTED' else 409 if status=='BUSY' else 429

    @app.post('/api/v1/market-insights/fii-holdings/import')
    def import_fii_holdings():
        upload=request.files.get('file')
        if upload is None:return jsonify(error='Choose a CSV file'),400
        try:result=service.fii_holdings_manager.import_csv(upload.stream.read(2_000_001))
        except (ValueError,UnicodeError) as exc:return jsonify(error=str(exc)),400
        return jsonify(result)
    # This is always loopback; Flask dev server is NOT for a public-facing deployment.
    @app.after_request
    def safe_headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; base-uri 'self'; object-src 'none'"
        return response

    @app.get('/api/v1/health')
    def health():return jsonify(service.health())

    @app.get('/api/v1/market-insights/<module>')
    def module(module):
        if module not in ('dashboard','pre-market','intraday','btst','btst-closing','index-options','fo-stocks','swing-trades','multibagger'):
            return jsonify(error='Unknown Market Insights module'),404
        return jsonify(service.snapshot(module))

    @app.get('/api/v1/market-insights/fii-stock-deals')
    def fii_stock_deals():
        try:return jsonify(service.fii_stock_deals(datetime.now(IST)))
        except (OSError,ValueError,RuntimeError):
            return jsonify(status='FII DEAL HISTORY UNAVAILABLE',bought=[],sold=[],
                data_scope='NSE disclosed bulk/block deals only'),503

    @app.post('/api/v1/market-insights/fii-stock-deals/refresh')
    def refresh_fii_stock_deals():
        result=service.request_fii_deals_refresh(datetime.now(IST))
        status=result.get('status')
        return jsonify(result),202 if status=='STARTED' else 409 if status=='ALREADY RUNNING' else 429 if status=='ALREADY ATTEMPTED' else 503

    @app.get('/api/v1/market-insights/participant-positioning')
    def participant_positioning():
        try:return jsonify(service.participant_positioning(datetime.now(IST)))
        except (ValueError,RuntimeError,OSError):
            return jsonify(status='UNAVAILABLE — NSE POSITION DATABASE',
                           participants={},overall_direction='UNAVAILABLE'),503

    @app.post('/api/v1/market-insights/participant-positioning/refresh')
    def participant_refresh():
        result=service.request_participant_refresh(datetime.now(IST))
        code=(202 if result['status']=='STARTED' else
              409 if result['status']=='REFRESH ALREADY RUNNING' else
              429 if result['status']=='ALREADY CHECKED IN THIS WINDOW' else 503)
        return jsonify(result),code

    @app.get('/api/v1/market-insights/analyse/choices')
    def analyse_choices():
        try:return jsonify(service.analyse_choices(datetime.now(IST)))
        except (ValueError,RuntimeError):
            return jsonify(status='UNAVAILABLE',indices=[],gainers=[],losers=[],
                           note='Dhan quote ranking unavailable'),503

    @app.get('/api/v1/market-insights/analyse')
    def analyse():
        symbol=(request.args.get('symbol') or '').strip()
        expiry=request.args.get('expiry')
        if not symbol:return jsonify(status='SEARCH',note='Enter a Dhan mapped stock or index symbol',disclaimer=DISCLAIMER)
        if len(symbol)>64:return jsonify(error='Invalid symbol'),400
        try:return jsonify(service.analyse(symbol,datetime.now(IST),expiry))
        except ValueError as exc:return jsonify(status='UNAVAILABLE',error=str(exc),disclaimer=DISCLAIMER),400
        except Exception:return jsonify(status='UNAVAILABLE',error='Licensed Dhan data/entitlement unavailable; no trade inferred',disclaimer=DISCLAIMER),503

    @app.post('/api/v1/market-insights/dashboard/refresh')
    def refresh_dashboard():
        # Local-only asynchronous historical data refresh. Never submits orders.
        result=service.request_dashboard_refresh()
        return jsonify(result),202 if result['status']=='STARTED' else (429 if result['status']=='RATE_LIMITED' else 409 if result['status']=='BUSY' else 503)

    @app.get('/api/v1/market-insights/readiness')
    def scanner_readiness():
        from insights.diagnostics import report
        return jsonify(report(service))

    @app.get('/api/v1/market-insights/track-record')
    def track_record():return jsonify(signals=service.journal.signals(),stats=service.journal.stats(),
         backtests=service.journal.backtests(),note='Open/research trades are not counted as wins. Only observed outcomes count.',disclaimer=DISCLAIMER)

    @app.get('/api/v1/market-insights/backtests')
    def backtests():return jsonify(backtests=service.journal.backtests(),
          status='UNVALIDATED UNTIL Dhan-funded historical backtests are run',disclaimer=DISCLAIMER)

    @app.get('/api/v1/market-insights/status')
    def status():return jsonify(service.health())

    @app.get('/')
    @app.get('/<path:resource>')
    def ui(resource=''):
        if not (path/'index.html').exists():
            return ('Frontend not built. Run INSTALL_INSIGHTS.bat to install and build React.',503)
        if resource and (path/resource).is_file():return send_from_directory(path,resource)
        return send_from_directory(path,'index.html')
    return app

