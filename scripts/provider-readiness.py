"""Verify licensed enrollment before the administrator enables the provider."""
import argparse
import json
import sqlite3
from pathlib import Path

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--username', required=True)
args = parser.parse_args()
state = args.root / 'bliss-mfa/.local/engine'
appliance = json.loads((state / 'appliance.json').read_text(encoding='utf-8-sig'))
try:
    with sqlite3.connect(Path(appliance['database_file']).as_uri() + '?mode=ro', uri=True) as db:
        user = db.execute('SELECT username FROM mfa_users WHERE lower(username)=lower(?) '
            'AND status=? AND protected_rdp=1', (args.username, 'active')).fetchone()
    if not user:
        raise ValueError('Enroll and verify this protected Windows account in the portal first')
    response = httpx.get(f"http://127.0.0.1:{appliance['agent_port']}/v1/status",
        headers={'Authorization': 'Bearer ' + appliance['agent_token']}, timeout=10, trust_env=False)
    response.raise_for_status()
    if response.json().get('state') not in {'active', 'offline_grace'}:
        raise ValueError('Activate your paid license before enabling RDP protection')
    print('Licensed enrollment verified')
except (httpx.HTTPError, sqlite3.Error, ValueError):
    raise SystemExit('Readiness failed. Verify the licensed, enrolled account in your local portal.') from None
