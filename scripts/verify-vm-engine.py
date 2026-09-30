"""Acceptance checks on the disposable VM using the installed provider client.

Never print OTPs, provisioning URIs, passwords, or shared secrets.
"""
import json
from pathlib import Path
import secrets
import subprocess
import time

import certifi
import httpx
import pyotp

ROOT = Path('C:/BlissMFA')
CONFIG = json.loads((ROOT / 'bliss-mfa/.local/engine/config.json').read_text())
USER = 'bliss_proto_test'
PROVIDER = Path('C:/Program Files/multiOTP')
CLIENT = ROOT / 'client-tests'
CLIENT.mkdir(exist_ok=True)
RESULTS = []


def record(name, passed):
    RESULTS.append({'test': name, 'passed': bool(passed)})
    print(('PASS ' if passed else 'FAIL ') + name, flush=True)
    if not passed:
        raise RuntimeError(name)


def request(method, path, **kwargs):
    response = httpx.request(method, 'http://127.0.0.1:18090' + path,
        headers={'Authorization': 'Bearer ' + CONFIG['adapter_token']}, timeout=20, **kwargs)
    response.raise_for_status()
    return response.json()


def check(code, *, secret=None, url=None):
    try:
        result = subprocess.run([str(PROVIDER / 'multiotp.exe'), '-cp',
            '-base-dir=' + CLIENT.as_posix() + '/', '-server-cache-level=0', '-server-timeout=2',
            '-server-url=' + (url or 'https://127.0.0.1:18443/auth'),
            '-server-secret=' + (secret or CONFIG['native_shared_secret']), USER, code],
            cwd=PROVIDER, capture_output=True, timeout=30)
        return result.returncode, b'multiOTP Credential Provider mode' in result.stdout
    except subprocess.TimeoutExpired:
        return 504, False


def fresh(otp):
    time.sleep(otp.interval - time.time() % otp.interval + .5)
    return otp.now()


try:
    record('management rejects unauthenticated requests',
        httpx.get('http://127.0.0.1:18090/v1/users').status_code == 401)
    record('engine user created', request('POST', '/v1/users', json={'username': USER})['ok'])
    uri = request('GET', f'/v1/users/{USER}/provisioning')['provisioning_uri']
    otp = pyotp.parse_uri(uri)
    code = otp.now()
    result, cp = check(code)
    record('installed provider executable accepts trusted fresh OTP', result == 0 and cp)
    record('accepted OTP replay rejected', check(code)[0] != 0)
    record('incorrect OTP rejected', check('000000')[0] != 0)
    record('incorrect shared secret rejected', check(otp.now(), secret=secrets.token_urlsafe(40))[0] != 0)
    record('native endpoint hides administration',
        httpx.get('https://127.0.0.1:18443/admin', verify=CONFIG['certificate_file']).status_code == 404)

    ca = PROVIDER / 'php/bliss-engine-ca.pem'
    original = ca.read_bytes()
    code = fresh(otp)
    try:
        ca.write_bytes(Path(certifi.where()).read_bytes())
        record('installed provider rejects untrusted engine certificate', check(code)[0] != 0)
    finally:
        ca.write_bytes(original)
    record('same OTP succeeds after restoring certificate trust', check(code)[0] == 0)

    record('disable succeeds', request('POST', f'/v1/users/{USER}/disable')['ok'])
    code = fresh(otp)
    record('disabled identity denied', check(code)[0] != 0)
    record('enable succeeds', request('POST', f'/v1/users/{USER}/enable')['ok'])
    record('enabled identity accepts fresh OTP', check(code)[0] == 0)
    record('lock succeeds', request('POST', f'/v1/users/{USER}/lock')['ok'])
    code = fresh(otp)
    record('locked identity denied', check(code)[0] != 0)
    record('unlock succeeds', request('POST', f'/v1/users/{USER}/unlock')['ok'])
    record('unlocked identity accepts fresh OTP', check(code)[0] == 0)
    record('revoke succeeds', request('POST', f'/v1/users/{USER}/revoke')['ok'])
    record('revoked identity denied', check(fresh(otp))[0] != 0)
    record('delete succeeds', request('DELETE', f'/v1/users/{USER}')['ok'])
    record('deleted identity denied', check(otp.now())[0] != 0)
    record('unavailable endpoint denied', check(otp.now(), url='https://127.0.0.1:18444/auth')[0] != 0)
    record('test account re-enrolled', request('POST', '/v1/users', json={'username': USER})['ok'])
    uri = request('GET', f'/v1/users/{USER}/provisioning')['provisioning_uri']
    # Remains private under the administrator-only deployment directory.
    (ROOT / 'prototype-test-account.json').write_text(json.dumps({
        'username': USER, 'windows_password': secrets.token_urlsafe(24) + '!aA7',
        'provisioning_uri': uri, 'rdp_address': '100.83.112.5',
    }, indent=2))
    record('replacement enrollment accepts fresh OTP', check(pyotp.parse_uri(uri).now())[0] == 0)
finally:
    (ROOT / 'acceptance-results.json').write_text(json.dumps(RESULTS, indent=2))

print(f'{len(RESULTS)} installed-engine checks passed; Windows interactive sign-in remains separate.', flush=True)
