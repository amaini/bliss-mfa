"""Verify installed client defaults and Windows password independently of the UI."""
import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import time

import pyotp

parser = argparse.ArgumentParser()
parser.add_argument('--outage', action='store_true')
args = parser.parse_args()
root = Path('C:/BlissMFA')
data = json.loads((root / 'prototype-test-account.json').read_text(encoding='utf-8-sig'))
config = json.loads((root / 'bliss-mfa/.local/engine/config.json').read_text())
otp = pyotp.parse_uri(data['provisioning_uri'])
time.sleep(otp.interval - time.time() % otp.interval + .5)
command = ['C:/Program Files/multiOTP/multiotp.exe', '-cp', '-server-cache-level=0',
    '-server-timeout=2', '-server-url=https://127.0.0.1:18443/auth',
    '-server-secret=' + config['native_shared_secret'], '-usersid=' + data['windows_sid'],
    data['username'], otp.now()]
try:
    result = subprocess.run(command, cwd='C:/Program Files/multiOTP', capture_output=True, timeout=30)
    passed = result.returncode != 0 if args.outage else result.returncode == 0
except subprocess.TimeoutExpired:
    # A timeout does not prove prompt fail-closed behavior.
    passed = False
name = 'actual client defaults deny engine outage' if args.outage else 'actual client defaults accept fresh OTP and Windows SID'
print(('PASS ' if passed else 'FAIL ') + name, flush=True)
results = [{'test': name, 'passed': passed}]
if not args.outage:
    api = ctypes.WinDLL('advapi32', use_last_error=True)
    logon = api.LogonUserW
    logon.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                     ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    logon.restype = ctypes.c_bool
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    for label, password, expected in [('Windows password accepted', data['windows_password'], True),
                                     ('wrong Windows password denied', data['windows_password'] + 'wrong', False)]:
        token = ctypes.c_void_p()
        accepted = logon(data['username'], 'WIN-10VM-ASUS', password, 2, 0, ctypes.byref(token))
        if accepted:
            kernel.CloseHandle(token)
        passed = accepted == expected
        results.append({'test': label, 'passed': passed})
        print(('PASS ' if passed else 'FAIL ') + label, flush=True)
output = root / ('outage-results.json' if args.outage else 'runtime-results.json')
output.write_text(json.dumps(results, indent=2))
if not all(row['passed'] for row in results):
    raise SystemExit(1)
