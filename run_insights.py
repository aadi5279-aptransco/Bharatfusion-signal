"""Local Flask/React entry point. Leaves the existing Tkinter app.py untouched."""
from __future__ import annotations
from pathlib import Path
import os


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent/'.env',override=False)
    except ImportError:pass


def main():
    _load_env()
    from insights.config import API_BIND,API_PORT
    from insights.api import create_app
    app=create_app()
    serve(app,API_BIND,API_PORT)


def serve(app,host,port):
    from werkzeug.serving import make_server
    server=make_server(host,port,app,threaded=True)
    service=app.extensions['insights_service']
    app.extensions['shutdown_server']=server.shutdown
    try:
        service.start()
        print(f'BharatSignal Market Insights: http://{host}:{port}  [READ-ONLY]')
        server.serve_forever()
    finally:
        try:service.stop()
        finally:server.server_close()

if __name__=='__main__':main()

