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
    app.extensions['insights_service'].start()
    print(f'BharatSignal Market Insights: http://{API_BIND}:{API_PORT}  [READ-ONLY]')
    app.run(host=API_BIND,port=API_PORT,debug=False,use_reloader=False,threaded=True)

if __name__=='__main__':main()
