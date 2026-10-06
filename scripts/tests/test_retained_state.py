"""Reinstall must reuse retained appliance data and never mint a replacement identity."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('appliance_runtime', SCRIPTS / 'appliance-runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def retained(tmp_path, *, identity=('installation.json', 'device.key'), evidence=('lease.token',),
             appliance=True):
    private = tmp_path / 'bliss-mfa/.local/engine'
    (private / 'state').mkdir(parents=True)
    (private / 'state/users.db').write_text('otp data')
    for name in ('engine-cert.pem', 'engine-cert.key'):
        (private / name).write_text('x')
    (private / 'config.json').write_text(json.dumps({
        'state_dir': str(private / 'state'), 'certificate_file': str(private / 'engine-cert.pem'),
        'certificate_key_file': str(private / 'engine-cert.key')}))
    license_state = private / 'license-state'
    license_state.mkdir()
    if appliance:
        (private / 'appliance.json').write_text(json.dumps({'license_state_dir': str(license_state)}))
    for name in identity:
        content = json.dumps({'installation_id': 'MFA-retained'}) if name == 'installation.json' else 'key'
        (license_state / name).write_text(content)
    for name in evidence:
        (license_state / name).write_text('x')
    return private


def test_empty_location_is_a_fresh_installation(tmp_path):
    assert runtime.inspect_retained(tmp_path / 'bliss-mfa/.local/engine')['mode'] == 'fresh'


def test_retained_identity_is_reused(tmp_path):
    result = runtime.inspect_retained(retained(tmp_path))
    assert result == {'mode': 'retained', 'installation_id': 'MFA-retained', 'activated': True}


def test_never_activated_appliance_can_be_reinstalled(tmp_path):
    result = runtime.inspect_retained(retained(tmp_path, identity=(), evidence=()))
    assert result['mode'] == 'retained' and result['installation_id'] is None


@pytest.mark.parametrize('identity', [(), ('installation.json',), ('device.key',)])
def test_lost_or_partial_identity_after_activation_fails_clearly(tmp_path, identity):
    private = retained(tmp_path, identity=identity)
    with pytest.raises(runtime.IdentityLost, match='identity'):
        runtime.inspect_retained(private)


def test_partial_identity_fails_even_without_a_lease(tmp_path):
    with pytest.raises(runtime.IdentityLost):
        runtime.inspect_retained(retained(tmp_path, identity=('device.key',), evidence=()))


def test_retained_data_without_engine_configuration_is_refused(tmp_path):
    private = retained(tmp_path)
    (private / 'config.json').unlink()
    with pytest.raises(runtime.RetainedStateError, match='configuration'):
        runtime.inspect_retained(private)


def test_appliance_reinstall_requires_retained_appliance_configuration(tmp_path):
    private = retained(tmp_path, appliance=False)
    with pytest.raises(runtime.RetainedStateError, match='appliance'):
        runtime.inspect_retained(private)
    assert runtime.inspect_retained(private, appliance=False)['mode'] == 'retained'


def test_missing_engine_certificate_is_refused(tmp_path):
    private = retained(tmp_path)
    (private / 'engine-cert.key').unlink()
    with pytest.raises(runtime.RetainedStateError, match='certificate'):
        runtime.inspect_retained(private)


def run_inspection(private):
    return subprocess.run([sys.executable, str(SCRIPTS / 'run-engine.py'), '--config', str(private / 'config.json'),
                           '--inspect-retained'], capture_output=True, text=True)


def test_installer_inspection_command_reports_retained_identity(tmp_path):
    result = run_inspection(retained(tmp_path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['installation_id'] == 'MFA-retained'


def test_installer_inspection_command_exits_distinctly_when_identity_is_lost(tmp_path):
    result = run_inspection(retained(tmp_path, identity=()))
    assert result.returncode == 3
    assert 'identity' in result.stderr.lower() and 'docs/reinstall' in result.stderr


def test_installation_id_without_key_before_activation_is_allowed(tmp_path):
    result = runtime.inspect_retained(retained(tmp_path, identity=('installation.json',), evidence=()))
    assert result['mode'] == 'retained' and result['installation_id'] == 'MFA-retained'
