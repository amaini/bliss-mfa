"""Private configuration and supervised processes for local appliance management."""
import html
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def initialize(engine_path, license_url, public_key_file):
    parsed = urlsplit(license_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use an HTTPS licensing server URL')
    key_bytes = public_key_file.read_bytes()
    if not isinstance(serialization.load_pem_public_key(key_bytes), Ed25519PublicKey):
        raise TypeError('Licensing key must be Ed25519')
    path = engine_path.parent / 'appliance.json'
    if path.exists():
        raise ValueError('Appliance configuration already exists')
    key_path = engine_path.parent / 'license-public.pem'
    key_path.write_bytes(key_bytes)
    config = {'company_name': 'Bliss Secure MFA', 'jwt_secret': secrets.token_urlsafe(48),
              'setup_token': secrets.token_urlsafe(40), 'agent_token': secrets.token_urlsafe(40),
              'license_url': license_url.rstrip('/'), 'public_key_file': str(key_path),
              'database_file': str(engine_path.parent / 'appliance.db'),
              'license_state_dir': str(engine_path.parent / 'license-state'),
              'api_port': 18091, 'agent_port': 18092, 'portal_port': 19043, 'tls_port': 19443}
    with path.open('x', encoding='utf-8') as stream:
        json.dump(config, stream, indent=2)
    welcome = engine_path.parent / 'Open-Appliance.html'
    url = 'https://localhost:19443/setup#token=' + config['setup_token']
    welcome.write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Bliss MFA setup</title><h1>Set up your Bliss MFA appliance</h1>'
        '<p>Open this private link on this Windows machine to create your local administrator.</p>'
        '<p><a href="' + html.escape(url, quote=True) + '">Start secure setup</a></p>'
        '<p>After setup, use <a href="https://localhost:19443">the local management portal</a>.</p></html>',
        encoding='utf-8')
    print('Private appliance configuration created')


def processes(repo, engine_config, state_parent, python):
    path = state_parent / 'appliance.json'
    if not path.exists():
        return []
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    work = repo.parent
    node = work / 'node/node.exe'
    portal = work / 'portal/server.js'
    if not node.is_file() or not portal.is_file():
        raise RuntimeError('Built portal or Node runtime missing')
    common = os.environ.copy()
    api_env = dict(common, PYTHONPATH=str(repo / 'apps/appliance-api'), APP_ENV='production',
        DATABASE_URL='sqlite+pysqlite:///' + Path(config['database_file']).as_posix(),
        JWT_SECRET=config['jwt_secret'], SETUP_TOKEN=config['setup_token'],
        COMPANY_NAME=config['company_name'], MULTIOTP_ADAPTER_URL=f"http://127.0.0.1:{engine_config['adapter_port']}",
        MULTIOTP_ADAPTER_TOKEN=engine_config['adapter_token'],
        LICENSE_AGENT_URL=f"http://127.0.0.1:{config['agent_port']}", LICENSE_AGENT_TOKEN=config['agent_token'])
    agent_env = dict(common, PYTHONPATH=str(repo / 'services/license-agent'),
        STATE_DIR=config['license_state_dir'], LICENSE_SERVER_URL=config['license_url'],
        AGENT_SHARED_TOKEN=config['agent_token'], BLISS_SIGNING_PUBLIC_KEY_FILE=config['public_key_file'])
    portal_env = dict(common, NODE_ENV='production', HOSTNAME='127.0.0.1', PORT=str(config['portal_port']),
        APPLIANCE_API_URL=f"http://127.0.0.1:{config['api_port']}", NEXT_TELEMETRY_DISABLED='1')
    proxy_env = dict(common, PYTHONPATH=str(repo / 'services/multiotp-adapter'),
        BLISS_PORTAL_TLS_PORT=str(config['tls_port']), BLISS_PORTAL_HTTP_PORT=str(config['portal_port']))
    def uvicorn(app, port):
        return [python, '-m', 'uvicorn', app, '--host', '127.0.0.1', '--port', str(port), '--no-access-log']
    # (name, command, environment, health check, TLS verification). These management
    # components are supervised separately from, and can never stop, authentication.
    return [
        ('license-agent', uvicorn('license_agent.main:app', config['agent_port']), agent_env,
            (f"http://127.0.0.1:{config['agent_port']}/health", {'Authorization': 'Bearer ' + config['agent_token']}), True),
        ('appliance-api', uvicorn('appliance.main:app', config['api_port']), api_env,
            (f"http://127.0.0.1:{config['api_port']}/health", {}), True),
        ('portal', [str(node), str(portal)], portal_env,
            (f"http://127.0.0.1:{config['portal_port']}/setup", {}), True),
        ('portal-tls', [*uvicorn('adapter.portal_proxy:app', config['tls_port']),
            '--ssl-certfile', engine_config['certificate_file'], '--ssl-keyfile', engine_config['certificate_key_file']], proxy_env,
            (f"https://localhost:{config['tls_port']}/setup", {}), engine_config['certificate_file']),
    ]
