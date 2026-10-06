"""Pinned build inputs: only content matching the recorded SHA-256 and size is ever used."""
import hashlib
import http.server
import importlib.util
import io
import json
import re
import threading
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location('fetch_inputs', ROOT / 'scripts/fetch-build-inputs.py')
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


@pytest.fixture
def origin(tmp_path):
    served = tmp_path / 'served'
    served.mkdir()

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(served), **kwargs)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield served, f'http://127.0.0.1:{server.server_address[1]}'
    server.shutdown()


def publish(served, name, data):
    (served / name).write_bytes(data)
    return {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}


def run(tmp_path, entries, cache=None):
    return fetch.fetch_all({'version': 1, 'inputs': entries}, tmp_path / 'out', cache_dir=cache, allow_http_loopback=True)


def test_verified_input_is_placed_at_its_target(origin, tmp_path):
    served, base = origin
    entry = {'name': 'winsw', 'urls': [base + '/WinSW-x64.exe'], 'target': 'inputs/WinSW-x64.exe',
             **publish(served, 'WinSW-x64.exe', b'wrapper')}
    run(tmp_path, [entry])
    assert (tmp_path / 'out/inputs/WinSW-x64.exe').read_bytes() == b'wrapper'


@pytest.mark.parametrize('field', ['sha256', 'size'])
def test_mismatched_content_is_rejected_and_never_written(origin, tmp_path, field):
    served, base = origin
    entry = {'name': 'node', 'urls': [base + '/node.exe'], 'target': 'node/node.exe',
             **publish(served, 'node.exe', b'node runtime')}
    entry[field] = 'f' * 64 if field == 'sha256' else 3
    with pytest.raises(fetch.InputError, match='node'):
        run(tmp_path, [entry])
    assert not (tmp_path / 'out/node/node.exe').exists()
    assert not list((tmp_path / 'out').rglob('*.part'))


def test_fallback_url_is_used_when_the_first_is_gone(origin, tmp_path):
    served, base = origin
    entry = {'name': 'php', 'urls': [base + '/missing.zip', base + '/archives.zip'], 'target': 'inputs/php.zip',
             **publish(served, 'archives.zip', b'php build')}
    run(tmp_path, [entry])
    assert (tmp_path / 'out/inputs/php.zip').read_bytes() == b'php build'


def zipped(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_archive_member_is_extracted_only_when_its_own_hash_matches(origin, tmp_path):
    served, base = origin
    data = zipped({'multiOTPCredentialProviderInstaller.msi': b'stock msi', 'readme.txt': b'x'})
    entry = {'name': 'provider', 'urls': [base + '/provider.zip'], **publish(served, 'provider.zip', data),
             'extract_member': {'name': 'multiOTPCredentialProviderInstaller.msi',
                                'sha256': hashlib.sha256(b'stock msi').hexdigest(),
                                'target': 'inputs/provider/multiOTPCredentialProviderInstaller.msi'}}
    run(tmp_path, [entry])
    assert (tmp_path / 'out/inputs/provider/multiOTPCredentialProviderInstaller.msi').read_bytes() == b'stock msi'
    entry['extract_member']['sha256'] = '0' * 64
    with pytest.raises(fetch.InputError, match='provider'):
        run(tmp_path / 'again', [entry])


def test_archive_can_be_unpacked_safely(origin, tmp_path):
    served, base = origin
    entry = {'name': 'php', 'urls': [base + '/php.zip'], 'unzip_to': 'work/php-runtime',
             **publish(served, 'php.zip', zipped({'php.exe': b'php', 'ext/php_openssl.dll': b'ssl'}))}
    run(tmp_path, [entry])
    assert (tmp_path / 'out/work/php-runtime/ext/php_openssl.dll').read_bytes() == b'ssl'
    traversal = {'name': 'evil', 'urls': [base + '/evil.zip'], 'unzip_to': 'work/evil',
                 **publish(served, 'evil.zip', zipped({'../escape.txt': b'x'}))}
    with pytest.raises(fetch.InputError, match='unsafe'):
        run(tmp_path, [traversal])


def test_verified_cache_is_reused_without_network(origin, tmp_path):
    served, base = origin
    entry = {'name': 'vc', 'urls': [base + '/vc.exe'], 'target': 'inputs/vc_redist.x64.exe',
             **publish(served, 'vc.exe', b'runtime')}
    cache = tmp_path / 'cache'
    run(tmp_path / 'first', [entry], cache)
    (served / 'vc.exe').unlink()
    run(tmp_path / 'second', [entry], cache)
    assert (tmp_path / 'second/out/inputs/vc_redist.x64.exe').read_bytes() == b'runtime'


def test_tampered_cache_entry_is_discarded(origin, tmp_path):
    served, base = origin
    entry = {'name': 'vc', 'urls': [base + '/vc.exe'], 'target': 'inputs/vc_redist.x64.exe',
             **publish(served, 'vc.exe', b'runtime')}
    cache = tmp_path / 'cache'
    run(tmp_path / 'first', [entry], cache)
    (cache / entry['sha256']).write_bytes(b'tampered')
    run(tmp_path / 'second', [entry], cache)
    assert (tmp_path / 'second/out/inputs/vc_redist.x64.exe').read_bytes() == b'runtime'


def test_plain_http_is_refused_outside_loopback_tests(tmp_path):
    with pytest.raises(fetch.InputError, match='HTTPS'):
        fetch.fetch_all({'version': 1, 'inputs': [{'name': 'x', 'urls': ['http://example.com/x'],
                                                   'target': 'x', 'sha256': '0' * 64, 'size': 1}]},
                        tmp_path / 'out')


def test_committed_manifest_pins_every_input():
    manifest = json.loads((ROOT / 'deployment/windows/build-inputs.json').read_text())
    names = {entry['name'] for entry in manifest['inputs']}
    assert {'python-embed', 'node', 'node-license', 'php', 'winsw', 'winsw-license', 'vc-redist',
            'provider'} <= names
    for entry in manifest['inputs']:
        assert entry['urls'] and all(url.startswith('https://') for url in entry['urls']), entry['name']
        assert re.fullmatch('[0-9a-f]{64}', entry['sha256']) and entry['size'] > 0, entry['name']
    provider = next(e for e in manifest['inputs'] if e['name'] == 'provider')
    # The stock SysCo 5.10.2.2 MSI the installer and uninstaller already pin.
    assert provider['extract_member']['sha256'] == '21fe0897c0056cfadd9fc741affb77c0cc7c87c86022a51a7cb9f7ab1c65cbd5'
    assert re.fullmatch('[0-9a-f]{40}', manifest['engine']['commit'])


def test_committed_wheel_lock_pins_a_hash_for_every_requirement():
    lock = (ROOT / 'deployment/windows/appliance-requirements.lock').read_text()
    blocks = re.split(r'\n(?=[a-z0-9])', lock.strip())
    requirements = [b for b in blocks if re.match(r'[a-z0-9][a-z0-9._-]*==', b)]
    assert len(requirements) >= 20
    assert all('--hash=sha256:' in block for block in requirements)
