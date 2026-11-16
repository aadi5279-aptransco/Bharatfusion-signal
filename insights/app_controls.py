"""Local-only application exit, guarded against cross-site shutdown requests."""
import secrets
import threading
from urllib.parse import urlsplit


def register(app):
    from flask import request,jsonify
    token=secrets.token_urlsafe(32)
    lock=threading.Lock()
    state={'requested':False}
    def local():
        return (request.remote_addr in ('127.0.0.1','::1') and
                urlsplit(request.host_url).hostname in ('127.0.0.1','localhost','::1') and
                request.headers.get('Origin',request.host_url.rstrip('/'))==request.host_url.rstrip('/'))
    @app.get('/api/v1/app/control')
    def control():
        if not local():return jsonify(error='Local same-origin requests only'),403
        return jsonify(can_exit=callable(app.extensions.get('shutdown_server')),token=token)
    @app.post('/api/v1/app/exit')
    def exit_app():
        if not local() or not secrets.compare_digest(request.headers.get('X-App-Control',''),token):
            return jsonify(error='Invalid local application control request'),403
        callback=app.extensions.get('shutdown_server')
        if not callable(callback):return jsonify(error='Restart using the updated START_INSIGHTS.bat launcher to enable Exit'),409
        with lock:
            if state['requested']:return jsonify(status='SHUTDOWN_REQUESTED'),202
            state['requested']=True
        response=jsonify(status='SHUTDOWN_REQUESTED')
        response.status_code=202
        # The HTTP body is sent before shutdown. Called in the request thread,
        # separate from the server's serve_forever thread, avoiding deadlock.
        response.call_on_close(callback)
        return response
