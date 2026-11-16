import json
import threading
import unittest
import urllib.request
from unittest.mock import Mock,patch
from flask import Flask
from insights.app_controls import register

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);register(self.app)
        self.client=self.app.test_client();self.stop=Mock()
        self.app.extensions['shutdown_server']=self.stop
        self.token=self.client.get('/api/v1/app/control').json['token']
    def test_exit_after_response_close_once(self):
        response=self.client.post('/api/v1/app/exit',headers={'X-App-Control':self.token})
        self.assertEqual(response.status_code,202);self.stop.assert_not_called()
        response.close();self.stop.assert_called_once()
        again=self.client.post('/api/v1/app/exit',headers={'X-App-Control':self.token});again.close()
        self.stop.assert_called_once()
    def test_remote_cross_origin_wrong_host_and_token_rejected(self):
        for kw in (dict(environ_overrides={'REMOTE_ADDR':'10.0.0.1'}),dict(headers={'Origin':'https://evil.example','X-App-Control':self.token}),dict(headers={'Host':'evil.example','X-App-Control':self.token}),dict(headers={'X-App-Control':'bad'})):
            r=self.client.post('/api/v1/app/exit',**kw);self.assertEqual(r.status_code,403)
        self.stop.assert_not_called()
        self.assertEqual(self.client.get('/api/v1/app/control',headers={'Host':'evil.example'}).status_code,403)
    def test_unsupported_launcher_and_get_do_not_exit(self):
        del self.app.extensions['shutdown_server']
        self.assertFalse(self.client.get('/api/v1/app/control').json['can_exit'])
        self.assertEqual(self.client.post('/api/v1/app/exit',headers={'X-App-Control':self.token}).status_code,409)
        self.assertEqual(self.client.get('/api/v1/app/exit').status_code,405)

class LauncherTests(unittest.TestCase):
    def test_live_server_exit_response_and_cleanup(self):
        from werkzeug.serving import make_server
        from run_insights import serve
        app=Flask(__name__);register(app);service=Mock();app.extensions['insights_service']=service
        server=make_server('127.0.0.1',0,app,threaded=True)
        url=f'http://127.0.0.1:{server.server_port}'
        with patch('werkzeug.serving.make_server',return_value=server):
            thread=threading.Thread(target=serve,args=(app,'127.0.0.1',server.server_port),daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(url+'/api/v1/app/control',timeout=5) as r:token=json.load(r)['token']
                request=urllib.request.Request(url+'/api/v1/app/exit',method='POST',data=b'',headers={'X-App-Control':token})
                with urllib.request.urlopen(request,timeout=5) as r:self.assertEqual(json.load(r)['status'],'SHUTDOWN_REQUESTED')
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive());service.start.assert_called_once();service.stop.assert_called_once()
            finally:
                if thread.is_alive():server.shutdown();thread.join(timeout=5)
    def test_start_failure_still_cleans_server(self):
        from run_insights import serve
        app=Flask(__name__);service=Mock();service.start.side_effect=RuntimeError('start failed');app.extensions['insights_service']=service
        server=Mock()
        with patch('werkzeug.serving.make_server',return_value=server),self.assertRaises(RuntimeError):serve(app,'127.0.0.1',0)
        service.stop.assert_called_once();server.server_close.assert_called_once()
