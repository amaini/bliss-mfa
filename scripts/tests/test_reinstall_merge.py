"""Reinstall replaces application binaries and never touches retained private data."""
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / 'Merge-ReinstallFiles.ps1'
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell installer step')

PRIVATE = ['bliss-mfa/.local/engine/config.json', 'bliss-mfa/.local/engine/appliance.json',
           'bliss-mfa/.local/engine/license-state/installation.json',
           'bliss-mfa/.local/engine/license-state/device.key',
           'bliss-mfa/.local/engine/license-state/lease.token',
           'bliss-mfa/.local/engine/license-state/rdp-seats.sqlite3',
           'bliss-mfa/.local/engine/state/users/alice.db', 'bliss-mfa/.local/engine/appliance.db',
           'provider-backup/multiotp.windows.before-tls.php', 'updates/pending/journal.json']


def write(root, names, prefix):
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prefix + name)


def digest(root, names):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def merge(root, staging):
    return subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT),
                           '-Root', str(root), '-Staging', str(staging)], capture_output=True, text=True)


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / 'BlissMFA'
    write(root, PRIVATE, 'private:')
    write(root, ['python/old.dll', 'portal/.next/old-chunk.js', 'php-runtime/old.dll', 'manifest.json',
                 'bliss-mfa/apps/appliance-api/appliance/removed.py', 'bliss-mfa/scripts/run-engine.py'], 'old:')
    staging = root / 'reinstall-staging'
    write(staging, ['python/python.exe', 'portal/server.js', 'php-runtime/php.exe', 'manifest.json',
                    'installers/vc_redist.x64.exe', 'multiotp-engine/multiotp.php',
                    'bliss-mfa/apps/appliance-api/appliance/main.py', 'bliss-mfa/scripts/run-engine.py',
                    'bliss-mfa/services/license-agent/license_agent/state.py',
                    'bliss-mfa/deployment/release-version.json'], 'new:')
    return root, staging


def test_reinstall_preserves_every_private_file_byte_for_byte(layout):
    root, staging = layout
    before = digest(root, PRIVATE)
    result = merge(root, staging)
    assert result.returncode == 0, result.stdout + result.stderr
    assert digest(root, PRIVATE) == before


def test_reinstall_replaces_binaries_and_removes_stale_files(layout):
    root, staging = layout
    assert merge(root, staging).returncode == 0
    assert (root / 'bliss-mfa/scripts/run-engine.py').read_text() == 'new:bliss-mfa/scripts/run-engine.py'
    assert (root / 'manifest.json').read_text() == 'new:manifest.json'
    for stale in ('python/old.dll', 'portal/.next/old-chunk.js', 'php-runtime/old.dll',
                  'bliss-mfa/apps/appliance-api/appliance/removed.py'):
        assert not (root / stale).exists(), stale
    assert (root / 'python/python.exe').exists()
    assert not staging.exists()


def test_reinstall_refuses_a_release_carrying_private_data(layout):
    root, staging = layout
    write(staging, ['bliss-mfa/.local/engine/config.json'], 'attacker:')
    before = digest(root, PRIVATE)
    assert merge(root, staging).returncode != 0
    assert digest(root, PRIVATE) == before
    assert (root / 'python/old.dll').exists()  # refused before any binary was removed


def test_reinstall_refuses_to_follow_a_linked_binary_directory(layout, tmp_path):
    root, staging = layout
    outside = tmp_path / 'outside'
    write(outside, ['keep.txt'], 'outside:')
    subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', str(root / 'php-runtime')], check=True)
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(root / 'php-runtime'), str(outside)],
                   check=True, capture_output=True)
    assert merge(root, staging).returncode != 0
    assert (outside / 'keep.txt').exists()
