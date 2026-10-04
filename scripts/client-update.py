"""Signed, administrator-approved application updates. Never updates the RDP provider."""
import argparse
import base64
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_SIZE = 512 * 1024 * 1024


class UpToDate(ValueError):
    pass


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Release version must be major.minor.patch')
    return tuple(map(int, value.split('.')))


def https(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Updates require an HTTPS URL without credentials or fragments')
    return value


def verify_manifest(envelope, key_bytes, current):
    payload = base64.b64decode(envelope['payload'], validate=True)
    key = serialization.load_pem_public_key(key_bytes)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError('Update signing key must be Ed25519')
    key.verify(base64.b64decode(envelope['signature'], validate=True), payload)
    release = json.loads(payload)
    if release['format'] != 1 or release['product'] != 'bliss-mfa-windows':
        raise ValueError('Unsupported release format or product')
    if version(release['version']) == version(current):
        raise UpToDate('Your application is up to date')
    if version(release['version']) < version(current):
        raise ValueError('Older releases cannot be installed')
    if version(current) < version(release['minimum_version']):
        raise ValueError('This release requires a newer installer or intermediate update')
    https(release['url'])
    if not re.fullmatch('[a-f0-9]{64}', release['sha256']):
        raise ValueError('Invalid release checksum')
    if type(release['size']) is not int or not 0 < release['size'] <= MAX_SIZE:
        raise ValueError('Invalid release size')
    return release


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or path.is_absolute()
            or name != path.as_posix() or any(p in ('.', '..') for p in name.split('/'))
            or path.parts[0] not in ('bliss-mfa', 'portal')
            or any((p.startswith('.') and not (p == '.next' and path.parts[0] == 'portal'))
                   or p.rstrip(' .') != p for p in path.parts)
            or any(re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p, re.I) for p in path.parts)):
        raise ValueError('Unsafe or private update path')
    return path


def unpack(archive, destination):
    seen = set()
    total = 0
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            # Explicit directory entries are unnecessary and not supported.
            path = safe_name(entry.filename)
            lower = str(path).lower()
            total += entry.file_size
            if lower in seen or total > MAX_SIZE * 4 or entry.is_dir() or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Duplicate, oversized or linked archive entry')
            seen.add(lower)
        if 'bliss-mfa/scripts/run-engine.py' not in seen or 'portal/server.js' not in seen:
            raise ValueError('Release missing required application entry points')
        for entry in package.infolist():
            target = destination.joinpath(*safe_name(entry.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)


def service(action):
    command = (f"{action}-Service -Name BlissMFAEngine -ErrorAction Stop; "
               f"(Get-Service BlissMFAEngine).WaitForStatus('{ 'Stopped' if action == 'Stop' else 'Running' }',[TimeSpan]::FromSeconds(60))")
    subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], check=True, timeout=90)


def readiness(root):
    config_path = root / 'bliss-mfa/.local/engine/config.json'
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    subprocess.run([str(root / 'python/python.exe'), str(root / 'bliss-mfa/scripts/run-engine.py'),
                    '--config', str(config_path), '--check'], check=True, timeout=180)
    service('Start')
    for _ in range(60):
        try:
            with httpx.Client(trust_env=False, timeout=2) as client:
                response = client.get(f"http://127.0.0.1:{config['adapter_port']}/health")
                if response.status_code == 200:
                    return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError('Updated service failed its health check')


def no_links(root):
    for path in [root, *root.rglob('*')]:
        if path.is_symlink() or path.is_junction():
            raise ValueError('Installation or update contains a link/junction')


def restore(root, transaction):
    journal = json.loads((transaction / 'journal.json').read_text())
    service('Stop')
    for name in journal['files']:
        target = root.joinpath(*safe_name(name).parts)
        old = transaction / 'old' / name
        if old.exists():
            shutil.copy2(old, target)
        else:
            target.unlink(missing_ok=True)
    private = root / 'bliss-mfa/.local'
    # Validated root-owned path only; never delete a computed external path.
    no_links(private)
    shutil.rmtree(private)
    shutil.copytree(transaction / 'private', private)
    readiness(root)
    (transaction / 'journal.json').unlink()


def apply(root, staged, transaction):
    private = (root / 'bliss-mfa/.local').resolve()
    config = json.loads((private / 'engine/config.json').read_text(encoding='utf-8-sig'))
    for key in ('state_dir', 'certificate_file', 'certificate_key_file'):
        if not Path(config[key]).resolve().is_relative_to(private):
            raise ValueError('Custom external engine state needs an installer migration')
    files = [p.relative_to(staged).as_posix() for p in staged.rglob('*') if p.is_file()]
    service('Stop')
    try:
        shutil.copytree(root / 'bliss-mfa/.local', transaction / 'private')
        for name in files:
            target = root / name
            if target.exists():
                old = transaction / 'old' / name
                old.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, old)
        journal = transaction / 'journal.tmp'
        journal.write_text(json.dumps({'files': files}))
        journal.replace(transaction / 'journal.json')
    except Exception:
        service('Start')
        raise
    try:
        for name in files:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged / name, target)
        readiness(root)
    except Exception:
        restore(root, transaction)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--feed', default='https://license.blissitek.ca/updates/stable.json')
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if os.name != 'nt' or not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError('Run the update shortcut as a Windows administrator')
    installed = json.loads(args.installation.read_text(encoding='utf-8-sig'))
    root = Path(installed['Root']).resolve(strict=True)
    no_links(root)
    workspace = root / 'updates'
    workspace.mkdir(exist_ok=True)
    lock = workspace / 'update.lock'
    with lock.open('x'):
        pass
    try:
        transaction = workspace / 'pending'
        if args.rollback:
            restore(root, transaction)
            previous = json.loads((transaction / 'installation.json').read_text())
            args.installation.write_text(json.dumps(previous))
            set_display_version(previous['Version'])
            print('Previous application and private state restored.')
            return
        if (transaction / 'journal.json').exists():
            raise RuntimeError('An interrupted update needs recovery. Run this command with --rollback first.')
        with httpx.Client(trust_env=False, timeout=60, follow_redirects=False) as client:
            data = bytearray()
            with client.stream('GET', https(args.feed)) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise ValueError('Release manifest too large')
            try:
                release = verify_manifest(json.loads(data), args.key.read_bytes(), installed['Version'])
            except UpToDate:
                print('Your application is up to date (' + installed['Version'] + ').')
                return
            print('Available version: ' + release['version'])
            print('Updating briefly interrupts MFA authentication. Keep recovery console access available.')
            if input('Type UPDATE to install, or Enter to cancel: ') != 'UPDATE':
                return
            if transaction.exists():
                shutil.rmtree(transaction)
            transaction.mkdir()
            archive = transaction / 'release.zip'
            with client.stream('GET', release['url']) as download, archive.open('xb') as output:
                download.raise_for_status()
                count = 0
                digest = hashlib.sha256()
                for chunk in download.iter_bytes():
                    count += len(chunk)
                    if count > release['size']:
                        raise ValueError('Release exceeds signed size')
                    digest.update(chunk)
                    output.write(chunk)
            if count != release['size'] or digest.hexdigest() != release['sha256']:
                raise ValueError('Release checksum or size mismatch')
        staged = transaction / 'staged'
        unpack(archive, staged)
        (transaction / 'installation.json').write_text(json.dumps(installed))
        apply(root, staged, transaction)
        try:
            set_display_version(release['version'])
            args.installation.write_text(json.dumps({**installed, 'Version': release['version']}))
        except Exception:
            restore(root, transaction)
            args.installation.write_text(json.dumps(installed))
            set_display_version(installed['Version'])
            raise
        (transaction / 'journal.json').unlink()
        print('Update complete. Accounts, enrollment and license retained.')
    finally:
        lock.unlink(missing_ok=True)


def set_display_version(value):
    version(value)
    subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                    "Set-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BlissMFA' DisplayVersion '" + value + "' -ErrorAction Stop"], check=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Update could not complete: ' + (str(error) or type(error).__name__))
        raise SystemExit(1) from None
