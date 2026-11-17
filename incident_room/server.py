"""Loopback-only dashboard API. Not an internet-ready authentication system."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import secrets
import threading
from urllib.parse import urlparse

from .agent import Investigator
from .store import Conflict
from .tools import scenario_by_id, scenarios


def make_server(store, port=8787):
    token = secrets.token_urlsafe(32)
    jobs = ThreadPoolExecutor(max_workers=2)
    slots = threading.BoundedSemaphore(2)

    def run_job(scenario, live, run_id):
        try:
            Investigator(store).investigate(scenario,live,run_id)
        finally:
            slots.release()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, data, content_type='application/json'):
            payload = json.dumps(data).encode() if content_type == 'application/json' else data.encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type+'; charset=utf-8')
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.end_headers()
            self.wfile.write(payload)

        def valid_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def do_GET(self):
            if not self.valid_host():
                return self.send(403,{'error':'Invalid local host'})
            path = urlparse(self.path).path
            try:
                if path == '/':
                    html = files('incident_room').joinpath('web/index.html').read_text(encoding='utf-8')
                    html = html.replace('/*BOOTSTRAP*/','window.INCIDENT_ROOM='+json.dumps({'api':True,'token':token})+';')
                    return self.send(200,html,'text/html')
                if path == '/api/scenarios':
                    return self.send(200,[{k:s[k] for k in ('id','title','alert','service')} for s in scenarios()])
                if path == '/api/runs':
                    return self.send(200,store.list())
                parts = path.strip('/').split('/')
                if len(parts) == 3 and parts[:2] == ['api','runs']:
                    return self.send(200,store.get(parts[2]))
                return self.send(404,{'error':'Not found'})
            except KeyError:
                return self.send(404,{'error':'Not found'})

        def do_POST(self):
            origin = self.headers.get('Origin')
            expected_origins = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
            if not self.valid_host() or (origin and origin not in expected_origins) or not secrets.compare_digest(self.headers.get('X-Incident-Room',''),token):
                return self.send(403,{'error':'Local session token and same-origin request required'})
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 1 <= length <= 8000:
                    return self.send(413,{'error':'Request must contain 1–8000 bytes'})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body,dict):
                    raise ValueError('Expected JSON object')
                path = urlparse(self.path).path
                if path == '/api/runs':
                    if set(body) != {'scenario','live'} or type(body['live']) is not bool:
                        raise ValueError('Expected scenario and boolean live fields')
                    scenario_by_id(body['scenario'])
                    if not slots.acquire(blocking=False):
                        return self.send(429,{'error':'Two investigations are already running'})
                    try:
                        run = store.create(body['scenario'],'live' if body['live'] else 'replay')
                        jobs.submit(run_job,body['scenario'],body['live'],run['id'])
                    except Exception:
                        slots.release()
                        raise
                    return self.send(202,run)
                parts = path.strip('/').split('/')
                if len(parts) == 5 and parts[:2] == ['api','runs'] and parts[3] == 'actions':
                    result = store.decide(parts[2],parts[4],body.get('decision'),body.get('version'),body.get('reason'))
                    return self.send(200,result)
                return self.send(404,{'error':'Not found'})
            except Conflict as error:
                return self.send(409,{'error':str(error)})
            except KeyError:
                return self.send(404,{'error':'Unknown run or action'})
            except (ValueError,TypeError) as error:
                return self.send(400,{'error':str(error)})

    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    return server, jobs


def serve(store,port=8787):
    server, jobs = make_server(store,port)
    print(f'Incident Room: http://127.0.0.1:{server.server_port}',flush=True)
    print('Local sandbox only. Live mode uses the API key in the server environment.',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        jobs.shutdown(wait=True)
