"""Isolated real-engine TLS/CGI regression, including legacy native HTTP framing.

Creates disposable state and never reads the enrolled Windows account.
"""
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import httpx
import pyotp

REPO = Path(__file__).resolve().parents[1]
WORK = REPO.parent

def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

def main():
    root = REPO / '.local' / ('cgi-validation-' + secrets.token_hex(6))
    config_path = root / 'config.json'
    launcher = REPO / 'scripts/run-engine.py'
    subprocess.run([sys.executable, str(launcher), '--initialize', '--config', str(config_path)], check=True)
    config = json.loads(config_path.read_text())
    config.update(auth_port=port(), adapter_port=port())
    config_path.write_text(json.dumps(config))
    child = subprocess.Popen([sys.executable, str(launcher), '--config', str(config_path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{config['adapter_port']}",
                          headers={'Authorization': 'Bearer ' + config['adapter_token']},
                          timeout=5, trust_env=False) as api:
            for _ in range(100):
                try:
                    if api.get('/health').status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if child.poll() is not None:
                    raise RuntimeError('Gateway startup failed')
                time.sleep(.1)
            else:
                raise RuntimeError('Gateway startup timeout')
            username = 'bliss_cgi_validation'
            response = api.post('/v1/users', json={'username': username})
            response.raise_for_status()
            response = api.get(f'/v1/users/{username}/provisioning')
            response.raise_for_status()
            otp = pyotp.parse_uri(response.json()['provisioning_uri'])
            if otp.interval - time.time() % otp.interval < 5:
                time.sleep(otp.interval - time.time() % otp.interval + .2)
            code = otp.now()
            command = [config['php_executable'], '-n', '-d',
                'extension_dir=' + config['php_extension_dir'], '-d', 'extension=mbstring',
                '-d', 'extension=openssl', '-d', 'openssl.cafile=' + config['certificate_file'],
                str(WORK / 'multiotp-engine/multiotp.php'), '-cp',
                '-base-dir=' + (root / 'client').as_posix() + '/',
                f"-server-url=https://127.0.0.1:{config['auth_port']}/auth",
                '-server-cache-level=0', '-server-timeout=2',
                '-server-secret=' + config['native_shared_secret'], username]
            for label, token, expected in [('fresh OTP', code, True), ('OTP replay', code, False),
                                           ('incorrect OTP', '000000', False)]:
                try:
                    result = subprocess.run([*command, token], stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=15, check=False)
                except subprocess.TimeoutExpired:
                    raise RuntimeError('Native client timeout') from None
                if (result.returncode == 0) != expected:
                    raise RuntimeError('Native authentication result mismatch')
                print('PASS ' + label, flush=True)
    finally:
        subprocess.run([sys.executable, str(launcher), '--stop', '--config', str(config_path)], check=False)
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()

if __name__ == '__main__':
    main()
