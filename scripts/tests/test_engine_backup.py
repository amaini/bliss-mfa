import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('engine_backup', Path(__file__).parents[1] / 'engine-backup.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PASSWORD = 'example test backup passphrase'


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'engine'
    root.mkdir()
    (root / 'state/users').mkdir(parents=True)
    (root / 'state/users/example.db').write_bytes(b'private authenticator seed')
    (root / 'engine-cert.pem').write_bytes(b'certificate')
    (root / 'engine-cert.key').write_bytes(b'private signing key')
    (root / 'config.json').write_text(json.dumps({
        'state_dir': str(root / 'state'), 'certificate_file': str(root / 'engine-cert.pem'),
        'certificate_key_file': str(root / 'engine-cert.key'), 'adapter_token': 'private token'}))
    return root


def test_encrypted_roundtrip_relocates_state(source, tmp_path):
    archive = tmp_path / 'snapshot.blissbackup'
    assert module.backup(source, archive, PASSWORD) == 5
    assert b'private' not in archive.read_bytes()
    restored = tmp_path / 'restored'
    assert module.restore(archive, restored, PASSWORD) == 5
    assert (restored / 'state/users/example.db').read_bytes() == b'private authenticator seed'
    config = json.loads((restored / 'config.json').read_text())
    assert config['state_dir'] == str(restored / 'state')
    assert config['adapter_token'] == 'private token'


def test_incorrect_password_and_corruption_leave_no_state(source, tmp_path):
    archive = tmp_path / 'snapshot.blissbackup'
    module.backup(source, archive, PASSWORD)
    target = tmp_path / 'restored'
    with pytest.raises(ValueError):
        module.restore(archive, target, 'different test passphrase')
    assert not target.exists()
    data = bytearray(archive.read_bytes())
    data[-10] ^= 1
    archive.write_bytes(data)
    with pytest.raises(ValueError):
        module.restore(archive, target, PASSWORD)
    assert not target.exists()


def test_existing_recovery_points_and_live_state_are_preserved(source, tmp_path):
    archive = tmp_path / 'snapshot.blissbackup'
    module.backup(source, archive, PASSWORD)
    original = archive.read_bytes()
    with pytest.raises(FileExistsError):
        module.backup(source, archive, PASSWORD)
    assert archive.read_bytes() == original
    with pytest.raises(ValueError):
        module.restore(archive, source, PASSWORD)


def test_external_state_is_rejected(source, tmp_path):
    config = json.loads((source / 'config.json').read_text())
    config['state_dir'] = str(tmp_path / 'elsewhere')
    (source / 'config.json').write_text(json.dumps(config))
    with pytest.raises(ValueError):
        module.backup(source, tmp_path / 'backup', PASSWORD)


def test_nested_certificate_and_appliance_paths_are_relocated(source, tmp_path):
    nested = source / 'certificates'
    nested.mkdir()
    (source / 'engine-cert.pem').rename(nested / 'engine-cert.pem')
    (source / 'engine-cert.key').rename(nested / 'engine-cert.key')
    config = json.loads((source / 'config.json').read_text())
    config.update(certificate_file=str(nested / 'engine-cert.pem'),
                  certificate_key_file=str(nested / 'engine-cert.key'))
    (source / 'config.json').write_text(json.dumps(config))
    (source / 'appliance.json').write_text(json.dumps({
        'database_file': str(source / 'appliance.db'),
        'license_state_dir': str(source / 'license-state'),
        'public_key_file': str(source / 'license-public.pem')}))
    archive = tmp_path / 'snapshot.blissbackup'
    module.backup(source, archive, PASSWORD)
    target = tmp_path / 'restored'
    module.restore(archive, target, PASSWORD)
    config = json.loads((target / 'config.json').read_text())
    assert config['certificate_file'] == str(target / 'certificates/engine-cert.pem')
    appliance = json.loads((target / 'appliance.json').read_text())
    assert appliance['database_file'] == str(target / 'appliance.db')
    assert appliance['license_state_dir'] == str(target / 'license-state')
    assert not (target / 'backup-layout.json').exists()


def test_reserved_metadata_filename_is_rejected(source, tmp_path):
    (source / 'backup-manifest.json').write_text('{}')
    with pytest.raises(ValueError):
        module.backup(source, tmp_path / 'backup', PASSWORD)
