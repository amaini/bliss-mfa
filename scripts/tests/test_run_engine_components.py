"""The real engine wiring: which processes form the authentication core."""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('run_engine', SCRIPTS / 'run-engine.py')
run_engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_engine)

CORE = {'native-auth', 'adapter'}
MANAGEMENT = {'license-agent', 'appliance-api', 'portal', 'portal-tls'}
COMMERCIAL_SECRETS = ('LICENSE', 'AGENT', 'JWT_SECRET', 'SETUP_TOKEN', 'BLISS_SIGNING')


def engine(tmp_path, appliance=True):
    root = tmp_path / 'BlissMFA'
    repo = root / 'bliss-mfa'
    private = repo / '.local/engine'
    private.mkdir(parents=True)
    for name in ('php-runtime/php.exe', 'php-runtime/php-cgi.exe', 'multiotp-engine/multiotp.php',
                 'multiotp-engine/multiotp.class.php', 'node/node.exe', 'portal/server.js'):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text('x')
    (root / 'php-runtime/ext').mkdir()
    config = {'state_dir': str(private / 'state'), 'php_executable': str(root / 'php-runtime/php.exe'),
              'php_extension_dir': str(root / 'php-runtime/ext'),
              'engine_cli': str(root / 'multiotp-engine/multiotp.php'),
              'engine_class': str(root / 'multiotp-engine/multiotp.class.php'),
              'adapter_token': 'adapter-secret', 'native_shared_secret': 'native-secret',
              'auth_bind': '127.0.0.1', 'auth_port': 18443, 'adapter_port': 18090,
              'certificate_file': str(private / 'engine-cert.pem'),
              'certificate_key_file': str(private / 'engine-cert.key')}
    for key in ('certificate_file', 'certificate_key_file'):
        Path(config[key]).write_text('x')
    if appliance:
        (private / 'appliance.json').write_text(json.dumps({
            'company_name': 'Test', 'jwt_secret': 'jwt', 'setup_token': 'setup', 'agent_token': 'agent',
            'license_url': 'https://license.example', 'public_key_file': str(private / 'license-public.pem'),
            'database_file': str(private / 'appliance.db'), 'license_state_dir': str(private / 'license-state'),
            'api_port': 18091, 'agent_port': 18092, 'portal_port': 19043, 'tls_port': 19443}))
    return repo, config


def test_authentication_core_is_only_native_auth_and_adapter(tmp_path):
    repo, config = engine(tmp_path)
    components = run_engine.components(config, repo=repo)
    assert {c.name for c in components if c.critical} == CORE
    assert {c.name for c in components if not c.critical} == MANAGEMENT
    assert all(c.health for c in components)


def test_authentication_core_receives_no_licensing_or_management_secrets(tmp_path):
    repo, config = engine(tmp_path)
    for component in run_engine.components(config, repo=repo):
        if component.critical:
            # Variables inherited from the host (e.g. a CI runner's AGENT_TOOLSDIRECTORY) are not added by
            # the launcher; only values it sets for the component can leak licensing or management secrets.
            leaked = [k for k in component.env if k.startswith(COMMERCIAL_SECRETS) and k not in os.environ]
            assert leaked == [], component.name


def test_engine_only_installation_runs_just_the_core(tmp_path):
    repo, config = engine(tmp_path, appliance=False)
    assert {c.name for c in run_engine.components(config, repo=repo)} == CORE


class FakeSupervisor:
    instances = []

    def __init__(self, components, **options):
        self.components, self.options, self.calls = components, options, []
        FakeSupervisor.instances.append(self)

    def start(self, check=False):
        self.calls.append(('start', check))

    def run(self, stopping, stop_file=None):
        self.calls.append(('run',))

    def stop(self):
        self.calls.append(('stop',))


@pytest.mark.parametrize('check', [True, False])
def test_serve_delegates_to_the_isolating_supervisor(tmp_path, monkeypatch, check):
    repo, config = engine(tmp_path)
    monkeypatch.setattr(run_engine, 'REPO', repo)
    monkeypatch.setattr(run_engine.engine_supervisor, 'Supervisor', FakeSupervisor)
    FakeSupervisor.instances.clear()
    run_engine.serve(config, check=check)
    calls = FakeSupervisor.instances[0].calls
    assert calls[0] == ('start', check)
    assert ('run',) in calls if not check else ('run',) not in calls
    assert calls[-1] == ('stop',)


def agent_env(tmp_path, version=None):
    repo, config = engine(tmp_path)
    if version:
        (repo / 'deployment').mkdir(parents=True, exist_ok=True)
        (repo / 'deployment/release-version.json').write_text(json.dumps({'version': version}))
    return next(c for c in run_engine.components(config, repo=repo) if c.name == 'license-agent').env


def test_license_agent_reports_the_installed_release_version(tmp_path):
    assert agent_env(tmp_path, '0.1.3')['SOFTWARE_VERSION'] == '0.1.3'


def test_missing_release_version_is_reported_as_unknown_not_a_real_version(tmp_path):
    assert agent_env(tmp_path)['SOFTWARE_VERSION'] == 'unknown'
