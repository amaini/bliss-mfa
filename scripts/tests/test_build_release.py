"""One command turns verified inputs into a verified customer release with recorded checksums."""
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SCRIPT = Path(__file__).resolve().parents[1] / 'build-release.py'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def fetched(tmp_path):
    root = tmp_path / 'fetched'
    files = ['inputs/WinSW-x64.exe', 'inputs/WINSW-LICENSE', 'inputs/vc_redist.x64.exe', 'inputs/NODE-LICENSE',
             'inputs/provider/multiOTPCredentialProviderInstaller.msi', 'node/node.exe', 'work/php-runtime/php.exe',
             'work/multiotp-engine/contrib/fixture.php']
    files += ['work/multiotp-engine/' + n for n in ('multiotp.php', 'multiotp.class.php', 'COPYING', 'COPYING.LESSER',
                                                    'README.md')]
    for name in files:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b'non-executable fixture ' + name.encode())
    with zipfile.ZipFile(root / 'inputs/python-embed.zip', 'w') as archive:
        archive.writestr('python.exe', b'fixture')
    (root / 'inputs/appliance-wheels').mkdir()
    with zipfile.ZipFile(root / 'inputs/appliance-wheels/fixture-1.0-py3-none-any.whl', 'w') as archive:
        archive.writestr('fixture/__init__.py', b'')
    portal = tmp_path / 'portal'
    for name in ('.next/standalone/server.js', '.next/static/chunk.js'):
        (portal / name).parent.mkdir(parents=True, exist_ok=True)
        (portal / name).write_text('portal fixture')
    key = tmp_path / 'license-public.pem'
    key.write_bytes(Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return root, portal, key


def build(tmp_path, fetched, *extra):
    root, portal, key = fetched
    return subprocess.run([sys.executable, str(SCRIPT), '--version', '0.1.3', '--inputs', str(root),
                           '--portal-build', str(portal), '--skip-portal-build', '--license-public-key', str(key),
                           '--output', str(tmp_path / 'release'), '--commit', 'a' * 40, *extra],
                          capture_output=True, text=True)


def test_test_build_produces_verified_labelled_artifacts(tmp_path, fetched):
    result = build(tmp_path, fetched, '--test-update-key')
    assert result.returncode == 0, result.stdout + result.stderr
    out = tmp_path / 'release'
    record = json.loads((out / 'release.json').read_text())
    installer = out / record['installer']['filename']
    assert 'TEST' in installer.name and record['test_build'] is True
    assert record['installer']['sha256'] == sha(installer)
    assert record['appliance']['sha256'] == sha(out / record['appliance']['filename'])
    assert record['update']['sha256'] == sha(out / record['update']['filename'])
    assert record['verification']['verified'] is True
    assert record['source_commit'] == 'a' * 40
    assert record['inputs_manifest_sha256'] and record['wheel_lock_sha256']
    assert (out / (installer.name + '.sha256')).read_text().split()[0] == record['installer']['sha256']


def test_test_signing_key_never_enters_customer_artifacts(tmp_path, fetched):
    assert build(tmp_path, fetched, '--test-update-key').returncode == 0
    out = tmp_path / 'release'
    for artifact in out.glob('*.zip'):
        with zipfile.ZipFile(artifact) as archive:
            for name in archive.namelist():
                if name.endswith('.zip'):
                    continue
                assert b'PRIVATE KEY' not in archive.read(name), (artifact.name, name)


def test_production_build_requires_the_pinned_update_key(tmp_path, fetched):
    result = build(tmp_path, fetched)
    assert result.returncode != 0
    assert 'update' in (result.stdout + result.stderr).lower()
    assert not list((tmp_path / 'release').glob('*.zip')) if (tmp_path / 'release').exists() else True


def test_production_build_rejects_an_unexpected_update_key(tmp_path, fetched):
    other = tmp_path / 'other-update.pem'
    other.write_bytes(Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    result = build(tmp_path, fetched, '--update-public-key', str(other))
    assert result.returncode != 0
    assert 'pinned' in (result.stdout + result.stderr).lower()
