import base64
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

spec = importlib.util.spec_from_file_location('updater', Path(__file__).parents[1] / 'client-update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def signed(**changes):
    key = Ed25519PrivateKey.generate()
    release = {'format': 1, 'product': 'bliss-mfa-windows', 'version': '0.1.2', 'minimum_version': '0.1.1',
               'url': 'https://license.example/updates/application.zip', 'sha256': 'a' * 64, 'size': 1024}
    release.update(changes)
    payload = json.dumps(release).encode()
    return ({'payload': base64.b64encode(payload).decode(), 'signature': base64.b64encode(key.sign(payload)).decode()},
            key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def test_signed_manifest():
    envelope, key = signed()
    assert updater.verify_manifest(envelope, key, '0.1.1')['version'] == '0.1.2'
    envelope['payload'] = base64.b64encode(b'{}').decode()
    with pytest.raises(InvalidSignature):
        updater.verify_manifest(envelope, key, '0.1.1')


def test_wrong_signing_key():
    envelope, _ = signed()
    _, other_key = signed()
    with pytest.raises(InvalidSignature):
        updater.verify_manifest(envelope, other_key, '0.1.1')


@pytest.mark.parametrize('changes', [{'version': '0.1.1'}, {'version': '0.1.0'},
                                   {'minimum_version': '0.2.0'}, {'url': 'http://example/x'},
                                   {'product': 'other'}, {'size': updater.MAX_SIZE + 1}])
def test_signed_but_incompatible(changes):
    envelope, key = signed(**changes)
    with pytest.raises(ValueError):
        updater.verify_manifest(envelope, key, '0.1.1')


@pytest.mark.parametrize('name', ['../x', 'bliss-mfa/../x', 'bliss-mfa/.local/config.json',
                                'portal/.env', 'portal/NUL.txt', 'portal/a:secret',
                                'python/python.exe', 'service/BlissMFAEngine.exe', 'portal/a\\b',
                                'portal/a.', 'portal//x'])
def test_reject_paths(name):
    with pytest.raises(ValueError):
        updater.safe_name(name)


def test_next_assets_allowed():
    assert updater.safe_name('portal/.next/static/app.js')


def test_duplicate_archive_is_not_extracted(tmp_path):
    archive = tmp_path / 'release.zip'
    with zipfile.ZipFile(archive, 'w') as package:
        package.writestr('portal/server.js', 'first')
        package.writestr('PORTAL/server.js', 'second')
    with pytest.raises(ValueError):
        updater.unpack(archive, tmp_path / 'staged')
    assert not (tmp_path / 'staged').exists()


def engine_config(root):
    private = root / 'bliss-mfa/.local/engine'
    private.mkdir(parents=True)
    (private / 'config.json').write_text(json.dumps({key: str(private / name) for key, name in
        [('state_dir', 'state'), ('certificate_file', 'cert.pem'), ('certificate_key_file', 'cert.key')]}))


def test_rollback_restores_files_and_database(tmp_path, monkeypatch):
    root, staged, transaction = (tmp_path / p for p in ('root', 'staged', 'transaction'))
    engine_config(root)
    (root / 'bliss-mfa/.local/appliance.db').write_bytes(b'original-database')
    (root / 'portal').mkdir()
    (root / 'portal/server.js').write_text('old')
    (staged / 'portal').mkdir(parents=True)
    (staged / 'portal/server.js').write_text('new')
    (staged / 'portal/new.js').write_text('new file')
    transaction.mkdir()
    actions = []
    monkeypatch.setattr(updater, 'service', actions.append)

    def readiness(target):
        if (target / 'portal/server.js').read_text() == 'new':
            (target / 'bliss-mfa/.local/appliance.db').write_bytes(b'migrated-database')
            raise RuntimeError('New service failed')
        actions.append('Recovered')

    monkeypatch.setattr(updater, 'readiness', readiness)
    with pytest.raises(RuntimeError, match='New service failed'):
        updater.apply(root, staged, transaction)
    assert (root / 'portal/server.js').read_text() == 'old'
    assert not (root / 'portal/new.js').exists()
    assert (root / 'bliss-mfa/.local/appliance.db').read_bytes() == b'original-database'
    assert actions == ['Stop', 'Stop', 'Recovered']
    assert not (transaction / 'journal.json').exists()


def test_success_preserves_private_state(tmp_path, monkeypatch):
    root, staged, transaction = (tmp_path / p for p in ('root', 'staged', 'transaction'))
    engine_config(root)
    (root / 'bliss-mfa/.local/seed').write_text('private')
    (staged / 'portal').mkdir(parents=True)
    (staged / 'portal/server.js').write_text('new')
    transaction.mkdir()
    monkeypatch.setattr(updater, 'service', lambda _: None)
    monkeypatch.setattr(updater, 'readiness', lambda _: None)
    updater.apply(root, staged, transaction)
    assert (root / 'bliss-mfa/.local/seed').read_text() == 'private'
    assert (transaction / 'private/seed').read_text() == 'private'
    assert (root / 'portal/server.js').read_text() == 'new'


def test_external_state_rejected_before_service_stop(tmp_path, monkeypatch):
    root = tmp_path / 'root'
    engine_config(root)
    config_path = root / 'bliss-mfa/.local/engine/config.json'
    config = json.loads(config_path.read_text())
    config['state_dir'] = str(tmp_path / 'external-state')
    config_path.write_text(json.dumps(config))
    actions = []
    monkeypatch.setattr(updater, 'service', actions.append)
    with pytest.raises(ValueError, match='external engine state'):
        updater.apply(root, tmp_path / 'stage', tmp_path / 'transaction')
    assert actions == []


def test_release_builder_signs_application_only(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('publisher', Path(__file__).parents[1] / 'publish-client-update.py')
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    key = Ed25519PrivateKey.generate()
    private = tmp_path / 'private.pem'
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    appliance = tmp_path / 'appliance.zip'
    with zipfile.ZipFile(appliance, 'w') as package:
        package.writestr('bliss-mfa/scripts/run-engine.py', 'engine')
        package.writestr('portal/server.js', 'portal')
        package.writestr('portal/.next/static/app.js', 'asset')
        package.writestr('python/python.exe', 'excluded runtime')
    output = tmp_path / 'update.zip'
    monkeypatch.setattr('sys.argv', ['publisher', '--appliance', str(appliance), '--output', str(output),
                                   '--key', str(private), '--version', '0.1.2', '--url', 'https://example/update.zip'])
    publisher.main()
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    release = updater.verify_manifest(json.loads(output.with_suffix('.signed.json').read_text()), public, '0.1.1')
    assert release['size'] == output.stat().st_size
    updater.unpack(output, tmp_path / 'staged')
    assert not (tmp_path / 'staged/python').exists()
