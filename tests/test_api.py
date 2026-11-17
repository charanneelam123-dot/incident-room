import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from incident_room.server import make_server
from incident_room.store import Store


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.folder.name)/'api.sqlite')
        self.server,self.jobs = make_server(self.store,0)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.root = f'http://127.0.0.1:{self.server.server_port}'
        with urllib.request.urlopen(self.root) as response:
            html = response.read().decode()
        self.token = json.loads(re.search(r'window.INCIDENT_ROOM=(\{[^;]+\});',html).group(1))['token']

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.jobs.shutdown(wait=True)
        self.thread.join()
        self.folder.cleanup()

    def post(self,path,body,token=True,origin=None):
        headers = {'Content-Type':'application/json'}
        if token:
            headers['X-Incident-Room'] = self.token
        if origin:
            headers['Origin'] = origin
        request = urllib.request.Request(self.root+path,data=json.dumps(body).encode(),headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status,json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code,json.load(error)

    def test_token_required(self):
        self.assertEqual(self.post('/api/runs',{'scenario':'checkout-pool','live':False},token=False)[0],403)

    def test_cross_origin_rejected(self):
        self.assertEqual(self.post('/api/runs',{'scenario':'checkout-pool','live':False},origin='https://other.example')[0],403)

    def test_bad_json_shape(self):
        self.assertEqual(self.post('/api/runs',[])[0],400)

    def test_invalid_live_flag(self):
        self.assertEqual(self.post('/api/runs',{'scenario':'checkout-pool','live':'yes'})[0],400)

    def test_full_api_investigate_then_decide(self):
        status,run = self.post('/api/runs',{'scenario':'checkout-pool','live':False})
        self.assertEqual(status,202)
        for _ in range(100):
            run = self.store.get(run['id'])
            if run['status'] not in {'queued','running'}:
                break
            time.sleep(.01)
        self.assertEqual(run['status'],'complete')
        path = '/api/runs/'+run['id']+'/actions/action-1'
        decision = {'decision':'approve','version':0,'reason':'Reviewed cited logs'}
        self.assertEqual(self.post(path,decision)[0],200)
        self.assertEqual(self.post(path,decision)[0],409)


if __name__ == '__main__':
    unittest.main()
