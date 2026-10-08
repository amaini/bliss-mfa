"""Private configuration and supervised processes for local appliance management."""
import html
import json
import os
import re
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


RECOVERY_DOC = 'docs/reinstall-and-identity-recovery.md'


def release_version(repo):
    """The single authoritative installed version, written by the build and replaced by signed updates."""
    try:
        version = json.loads((repo / 'deployment/release-version.json').read_text(encoding='utf-8-sig'))['version']
    except (OSError, ValueError, KeyError):
        return 'unknown'
    return version if isinstance(version, str) and re.fullmatch(r'\d+\.\d+\.\d+', version) else 'unknown'


IDENTITY_FILES = ('installation.json', 'device.key')
ACTIVATION_EVIDENCE = ('lease.token', 'trusted-time.json', 'released.json')


class RetainedStateError(ValueError):
    pass


class IdentityLost(RetainedStateError):
    pass


def inspect_retained(private, appliance=True):
    """Classify retained data before a reinstall. Never creates or repairs an identity."""
    private = Path(private)
    config_path = private / 'config.json'
    if not config_path.exists():
        if private.exists() and any(private.iterdir()):
            raise RetainedStateError('Retained data exists but its engine configuration is missing; '
                                     'restore it from backup. See ' + RECOVERY_DOC)
        return {'mode': 'fresh'}
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    for key in ('certificate_file', 'certificate_key_file'):
        if not Path(config[key]).is_file():
            raise RetainedStateError('Retained engine certificate is missing; restore it from backup. See ' + RECOVERY_DOC)
    result = {'mode': 'retained', 'installation_id': None, 'activated': False}
    appliance_path = private / 'appliance.json'
    if not appliance_path.exists():
        if appliance:
            raise RetainedStateError('Retained appliance configuration is missing; restore it from backup. See '
                                     + RECOVERY_DOC)
        return result
    license_state = Path(json.loads(appliance_path.read_text(encoding='utf-8-sig'))['license_state_dir'])
    present = [name for name in IDENTITY_FILES if (license_state / name).is_file()]
    result['activated'] = any((license_state / name).exists() for name in ACTIVATION_EVIDENCE)
    if (result['activated'] and len(present) < 2) or present == ['device.key']:
        raise IdentityLost('The retained appliance identity is incomplete or missing although this appliance '
                           'was activated. Reinstalling will not create a replacement identity. Restore the '
                           'license-state backup, or follow ' + RECOVERY_DOC + ' to have Bliss release the license.')
    if present:
        result['installation_id'] = json.loads((license_state / 'installation.json').read_text())['installation_id']
    return result


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
        LICENSE_AGENT_URL=f"http://127.0.0.1:{config['agent_port']}", LICENSE_AGENT_TOKEN=config['agent_token'],
        ENGINE_CONFIG_FILE=str(state_parent / 'config.json'),
        PROVIDER_VALIDATION_DIR=str(repo.parent / 'provider-validation'))
    agent_env = dict(common, PYTHONPATH=str(repo / 'services/license-agent'),
        STATE_DIR=config['license_state_dir'], LICENSE_SERVER_URL=config['license_url'],
        AGENT_SHARED_TOKEN=config['agent_token'], BLISS_SIGNING_PUBLIC_KEY_FILE=config['public_key_file'],
        SOFTWARE_VERSION=release_version(repo))
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
