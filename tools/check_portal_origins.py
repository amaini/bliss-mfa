"""Test a built portal against a loopback-only dummy backend; creates no accounts."""
import argparse
import http.server
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--portal', type=Path, required=True)
parser.add_argument('--node', default='node')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
portal = args.portal.resolve()
forwarded = []


class Backend(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', '0')))
        forwarded.append(self.path)
        self.send_response(422)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"detail":"isolated test backend"}')

    def log_message(self, *unused):
        pass


backend = http.server.HTTPServer(('127.0.0.1', 0), Backend)
threading.Thread(target=backend.serve_forever, daemon=True).start()
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
base = 'http://127.0.0.1:' + str(port)
env = dict(os.environ, NEXT_TELEMETRY_DISABLED='1',
           APPLIANCE_API_URL='http://127.0.0.1:' + str(backend.server_port))
child = subprocess.Popen([args.node, str(portal / 'node_modules/next/dist/bin/next'),
                          'start', '--hostname', '127.0.0.1', '--port', str(port)],
                         cwd=portal, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
rows = []
try:
    with httpx.Client(base_url=base, trust_env=False, timeout=10) as client:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError('Portal exited during startup')
            try:
                if client.get('/login').status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.2)
        else:
            raise RuntimeError('Portal startup timed out')
        for path in ['/login', '/setup']:
            response = client.get(path)
            rows.append({'test': path + ' page', 'passed': response.status_code == 200})
        response = client.get('/users')
        rows.append({'test': 'anonymous management redirects',
                     'passed': response.status_code in (302, 307, 308)
                     and '/login' in response.headers.get('location', '')})
        cases = [('foreign origin', {'Origin': 'https://attacker.example'}, False),
                 ('opaque origin', {'Origin': 'null'}, False),
                 ('cross-site without origin', {'Sec-Fetch-Site': 'cross-site'}, False),
                 ('same origin', {'Origin': base, 'Sec-Fetch-Site': 'same-origin'}, True),
                 ('native request without origin', {}, True)]
        for endpoint in ['bootstrap', 'login', 'backend']:
            for label, headers, allowed in cases:
                before = len(forwarded)
                path = '/api/backend/v1/users' if endpoint == 'backend' else '/api/auth/' + endpoint
                test_headers = dict(headers)
                if endpoint == 'backend':
                    test_headers['Cookie'] = 'bliss_appliance_session=isolated-dummy-token'
                response = client.post(path, json={}, headers=test_headers)
                reached = len(forwarded) > before
                rows.append({'test': endpoint + ': ' + label,
                             'passed': response.status_code == (422 if allowed else 403)
                             and reached == allowed,
                             'http': response.status_code, 'reached_dummy_backend': reached})
finally:
    if os.name == 'nt':
        subprocess.run(['taskkill.exe', '/PID', str(child.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        child.terminate()
    child.wait(timeout=10)
    backend.shutdown()
    backend.server_close()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(rows, indent=2))
print(str(sum(row['passed'] for row in rows)) + '/' + str(len(rows)) + ' checks passed')
raise SystemExit(0 if all(row['passed'] for row in rows) else 1)
