"""Fetch the pinned third-party inputs for the Windows appliance release and verify every byte.

Each input is used only when its SHA-256 and size match deployment/windows/build-inputs.json.
Archive members are verified again after extraction. Wheels come from the hash-locked
deployment/windows/appliance-requirements.lock (pip --require-hashes). The patched multiOTP
engine is exported from its pinned commit. Output layout matches build-vm-package.py:

  OUT/inputs/    python-embed.zip, WinSW-x64.exe, WINSW-LICENSE, vc_redist.x64.exe,
                 NODE-LICENSE, provider/multiOTPCredentialProviderInstaller.msi, appliance-wheels/
  OUT/node/      node.exe
  OUT/work/      php-runtime/, multiotp-engine/
"""
import argparse
import hashlib
import io
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / 'deployment/windows/build-inputs.json'
LOCK = REPO / 'deployment/windows/appliance-requirements.lock'
USER_AGENT = 'bliss-mfa-release-build'


class InputError(RuntimeError):
    pass


def _check_url(url, allow_http_loopback):
    parts = urlsplit(url)
    if parts.scheme == 'https' and parts.hostname:
        return
    if allow_http_loopback and parts.scheme == 'http' and parts.hostname and ipaddress.ip_address(parts.hostname).is_loopback:
        return
    raise InputError('Build inputs must use HTTPS: ' + url)


def _matches(path, sha256, size):
    if not path.is_file() or path.stat().st_size != size:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == sha256


def _safe_target(root, relative):
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise InputError('unsafe target path: ' + relative)
    return target


def _download(entry, destination, allow_http_loopback):
    errors = []
    for url in entry['urls']:
        _check_url(url, allow_http_loopback)
        partial = destination.with_name(destination.name + '.part')
        try:
            request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            digest, written = hashlib.sha256(), 0
            with urllib.request.urlopen(request, timeout=120) as response, partial.open('wb') as output:
                while chunk := response.read(1 << 20):
                    written += len(chunk)
                    if written > entry['size']:
                        raise InputError('larger than pinned size')
                    digest.update(chunk)
                    output.write(chunk)
            if written != entry['size'] or digest.hexdigest() != entry['sha256']:
                raise InputError(f'got {written} bytes sha256 {digest.hexdigest()}')
            partial.replace(destination)
            return
        except (OSError, InputError) as error:
            errors.append(f'{url}: {error}')
        finally:
            partial.unlink(missing_ok=True)
    raise InputError(f"{entry['name']}: no URL served the pinned content "
                     f"(sha256 {entry['sha256']}, {entry['size']} bytes): " + '; '.join(errors))


def _obtain(entry, staging, cache_dir, allow_http_loopback):
    """Return a verified local copy of the entry's file."""
    if cache_dir is not None:
        cached = cache_dir / entry['sha256']
        if _matches(cached, entry['sha256'], entry['size']):
            return cached
        cached.unlink(missing_ok=True)
    downloaded = staging / entry['sha256']
    _download(entry, downloaded, allow_http_loopback)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(downloaded, cache_dir / entry['sha256'])
    return downloaded


def _place(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.part')
    shutil.copy2(source, partial)
    partial.replace(target)


def _unzip(archive, destination, name):
    with zipfile.ZipFile(archive) as package:
        members = []
        for info in package.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts or ':' in info.filename or '\\' in info.filename:
                raise InputError(f'{name}: unsafe archive path {info.filename}')
            members.append(info)
        temporary = destination.with_name(destination.name + '.part')
        shutil.rmtree(temporary, ignore_errors=True)
        for info in members:
            if not info.is_dir():
                target = temporary.joinpath(*PurePosixPath(info.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(info) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
    shutil.rmtree(destination, ignore_errors=True)
    temporary.replace(destination)


def fetch_all(manifest, output, cache_dir=None, allow_http_loopback=False):
    if manifest.get('version') != 1:
        raise InputError('Unsupported build-input manifest version')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as scratch:
        staging = Path(scratch)
        for entry in manifest['inputs']:
            for url in entry['urls']:
                _check_url(url, allow_http_loopback)
            local = _obtain(entry, staging, Path(cache_dir) if cache_dir else None, allow_http_loopback)
            if 'target' in entry:
                _place(local, _safe_target(output, entry['target']))
            if 'extract_member' in entry:
                member = entry['extract_member']
                with zipfile.ZipFile(local) as package:
                    data = package.read(member['name'])
                if hashlib.sha256(data).hexdigest() != member['sha256']:
                    raise InputError(f"{entry['name']}: extracted {member['name']} does not match its pinned hash")
                target = _safe_target(output, member['target'])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            if 'unzip_to' in entry:
                _unzip(local, _safe_target(output, entry['unzip_to']), entry['name'])
    return output


def export_engine(engine, output, repository=REPO):
    """Export the pinned engine commit (content-addressed) without a working checkout."""
    target = _safe_target(Path(output), engine['target'])
    archive = subprocess.run(['git', '-C', str(repository), 'archive', '--format=tar', engine['commit']],
                             check=True, capture_output=True).stdout
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as package:
        package.extractall(target, filter='data')
    return target


def download_wheels(output, lock=LOCK, python=sys.executable):
    wheels = Path(output) / 'inputs/appliance-wheels'
    shutil.rmtree(wheels, ignore_errors=True)
    wheels.mkdir(parents=True)
    subprocess.run([python, '-m', 'pip', 'download', '--disable-pip-version-check', '--no-deps',
                    '--require-hashes', '--only-binary=:all:', '--platform', 'win_amd64',
                    '--python-version', '3.12', '--implementation', 'cp', '--abi', 'cp312',
                    '-r', str(lock), '-d', str(wheels)], check=True)
    return wheels


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    parser.add_argument('--cache', type=Path, default=os.environ.get('BLISS_BUILD_INPUT_CACHE'))
    parser.add_argument('--skip-wheels', action='store_true')
    parser.add_argument('--skip-engine', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    fetch_all(manifest, args.output, cache_dir=args.cache)
    if not args.skip_engine:
        export_engine(manifest['engine'], args.output)
    if not args.skip_wheels:
        download_wheels(args.output)
    print('Verified build inputs in ' + str(args.output.resolve()))


if __name__ == '__main__':
    try:
        main()
    except InputError as error:
        print('Build input verification failed: ' + str(error), file=sys.stderr)
        raise SystemExit(2) from None
