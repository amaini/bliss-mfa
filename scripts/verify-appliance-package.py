"""Exercise the packaged Windows appliance with isolated state and credentials."""
import argparse
import json
import secrets
import socket
import ssl
import subprocess
import time
import zipfile
from pathlib import Path

import httpx


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def verify(archive, directory):
    directory.mkdir(parents=True, exist_ok=False)
    account = subprocess.check_output(['whoami.exe'], text=True).strip()
    subprocess.run(['icacls.exe', str(directory), '/inheritance:r', '/grant:r',
        '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F', account + ':(OI)(CI)F'],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with zipfile.ZipFile(archive) as package:
        for name in package.namelist():
            if not (directory / name).resolve().is_relative_to(directory.resolve()):
                raise RuntimeError('Unsafe package path')
        package.extractall(directory)
    python = str(directory / 'python/python.exe')
    launcher = str(directory / 'bliss-mfa/scripts/run-engine.py')
    config_path = directory / 'bliss-mfa/.local/engine/config.json'
    subprocess.run([python, launcher, '--initialize'], check=True, stdout=subprocess.DEVNULL)
    config = json.loads(config_path.read_text())
    config.update(auth_port=free_port(), adapter_port=free_port())
    config_path.write_text(json.dumps(config))
    subprocess.run([python, launcher, '--initialize-appliance',
        '--license-url', 'https://license.blissitek.ca',
        '--public-key', str(directory / 'bliss-mfa/deployment/license-public.pem')],
        check=True, stdout=subprocess.DEVNULL)
    appliance_path = config_path.parent / 'appliance.json'
    appliance = json.loads(appliance_path.read_text())
    appliance.update({key: free_port() for key in
                      ('api_port', 'agent_port', 'portal_port', 'tls_port')})
    appliance_path.write_text(json.dumps(appliance))
    child = subprocess.Popen([python, launcher], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    checks = []
    def require(condition, name):
        if not condition:
            raise RuntimeError('Failed check: ' + name)
        checks.append(name)
        print('PASS ' + name, flush=True)
    try:
        origin = 'https://localhost:' + str(appliance['tls_port'])
        context = ssl.create_default_context(cafile=config['certificate_file'])
        with httpx.Client(base_url=origin, verify=context, timeout=20, trust_env=False) as client:
            for _ in range(100):
                try:
                    if client.get('/setup').status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if child.poll() is not None:
                    raise RuntimeError('Packaged component exited; inspect private logs')
                time.sleep(.2)
            else:
                raise RuntimeError('Packaged portal startup timed out')
            require(True, 'trusted TLS setup page')
            require(client.get('/api/backend/v1/onboarding').status_code == 401,
                    'anonymous management denied')
            require(client.get('/setup', headers={'Host': 'untrusted.example'}).status_code == 400,
                    'foreign host denied')
            payload = {'setup_token': appliance['setup_token'], 'email': 'owner@example.com',
                       'password': secrets.token_urlsafe(32)}
            require(client.post('/api/auth/bootstrap', json=payload,
                    headers={'Origin': 'https://untrusted.example'}).status_code == 403,
                    'foreign origin bootstrap denied')
            response = client.post('/api/auth/bootstrap', json=payload, headers={'Origin': origin})
            require(response.status_code == 200, 'owner bootstrap through production portal')
            cookie = response.headers.get('set-cookie', '').lower()
            require(all(part in cookie for part in ('httponly', 'secure', 'samesite=strict')),
                    'secure owner session cookie')
            require(client.post('/api/auth/bootstrap', json=payload).status_code == 409,
                    'second bootstrap denied')
            response = client.get('/api/backend/v1/onboarding')
            require(response.status_code == 200 and response.json()['complete'] is False,
                    'authenticated onboarding checklist')
            response = client.post('/api/backend/v1/users', headers={'Origin': origin},
                json={'username': 'package_probe', 'display_name': 'Package validation', 'protected_rdp': True})
            require(response.status_code == 403, 'unlicensed protected user creation denied')
            client.cookies.clear()
            response = client.post('/api/auth/login', json={'email': payload['email'],
                'password': 'incorrect-password'}, headers={'Origin': origin})
            require(response.status_code == 401, 'incorrect owner password denied')
            response = client.post('/api/auth/login', json={'email': payload['email'],
                'password': payload['password']}, headers={'Origin': origin})
            require(response.status_code == 200, 'owner can sign in again')
        (directory / 'verification-results.json').write_text(json.dumps({'passed': checks}, indent=2))
    finally:
        subprocess.run([python, launcher, '--stop'], check=False, stdout=subprocess.DEVNULL)
        try:
            child.wait(timeout=35)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    verify(args.archive, args.destination)
