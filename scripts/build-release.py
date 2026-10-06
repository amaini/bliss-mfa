"""Build the Windows customer release from verified inputs and record its checksums.

Inputs come from scripts/fetch-build-inputs.py. Steps: production portal build (stable
build ID = source commit), appliance archive, customer installer wrapper, verification,
release.json with every SHA-256. Archives are reproducible (SOURCE_DATE_EPOCH = commit time).

Production builds embed the pinned production update public key and are not signed here:
sign the update offline with publish-client-update.py on the signing computer.
--test-update-key builds a clearly labelled -TEST release with a throwaway update key
so the signed-update path can be exercised end to end; never ship it to customers.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / 'scripts'
KEYS = REPO / 'deployment/windows/keys'
# Production update-signing public key recorded for pilot RC2 (docs/pilot-release-0.1.2-validation.md).
PINNED_UPDATE_KEY_SHA256 = '6d37a5b11ad0bb606d2c65ed10c98ea437b8e9503937a6a9382ce001ad153d42'
TEST_UPDATE_URL = 'https://license.blissitek.ca/updates/test/bliss-mfa-update-{version}-TEST.zip'
UPDATE_URL = 'https://license.blissitek.ca/updates/bliss-mfa-update-{version}.zip'


class ReleaseError(RuntimeError):
    pass


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        raise ReleaseError('Step failed: ' + ' '.join(map(str, command[:3])) + '\n' + result.stdout + result.stderr)
    return result.stdout


def source_date_epoch(commit):
    if os.environ.get('SOURCE_DATE_EPOCH'):
        return os.environ['SOURCE_DATE_EPOCH']
    try:
        return run(['git', '-C', str(REPO), 'show', '-s', '--format=%ct', commit]).strip()
    except (ReleaseError, OSError):
        return '315532800'


def build_portal(portal, commit):
    npm = shutil.which('npm')
    if not npm:
        raise ReleaseError('npm is required on the build machine to build the portal')
    env = dict(os.environ, BLISS_BUILD_ID=commit, NEXT_TELEMETRY_DISABLED='1')
    shutil.rmtree(portal / '.next', ignore_errors=True)
    run([npm, 'ci', '--no-audit', '--no-fund'], cwd=portal, env=env)
    run([npm, 'run', 'build'], cwd=portal, env=env)


def update_key(args, out):
    if args.test_update_key:
        signing = out / 'test-signing'
        signing.mkdir()
        private = Ed25519PrivateKey.generate()
        (signing / 'update-private-TEST.pem').write_bytes(private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        public = signing / 'update-public-TEST.pem'
        public.write_bytes(private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        return public, signing / 'update-private-TEST.pem'
    public = args.update_public_key or KEYS / 'update-public.pem'
    if not public.is_file():
        raise ReleaseError('Production builds need the pinned update public key at ' + str(public) +
                           ' (expected SHA-256 ' + PINNED_UPDATE_KEY_SHA256 + '). Use --test-update-key for test builds.')
    if sha256(public) != PINNED_UPDATE_KEY_SHA256:
        raise ReleaseError('Update public key does not match the pinned production key ' + PINNED_UPDATE_KEY_SHA256)
    return public, None


def verify_customer_artifacts(appliance, installer):
    """Checks that apply to every build, signed or not."""
    with zipfile.ZipFile(appliance) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read('manifest.json'))
        if set(manifest) != set(names) - {'manifest.json'}:
            raise ReleaseError('Appliance manifest does not cover every file')
        for name, expected in manifest.items():
            data = archive.read(name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ReleaseError('Appliance file hash mismatch: ' + name)
            if b'PRIVATE KEY-----' in data or '.local/' in name:
                raise ReleaseError('Private material in appliance: ' + name)
    appliance_hash = sha256(appliance)
    with zipfile.ZipFile(installer) as archive:
        with archive.open('BlissMFA-Appliance.zip') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != appliance_hash:
                raise ReleaseError('Installer embeds a different appliance archive')
        if appliance_hash.encode() not in archive.read('Setup-BlissMFA.ps1'):
            raise ReleaseError('Installer setup does not pin the appliance SHA-256')
        for name in archive.namelist():
            if name != 'BlissMFA-Appliance.zip' and b'PRIVATE KEY-----' in archive.read(name):
                raise ReleaseError('Private material in installer: ' + name)
    return {'appliance_files': len(manifest), 'installer_pins_appliance_sha256': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', required=True)
    parser.add_argument('--inputs', type=Path, required=True, help='Output directory of fetch-build-inputs.py')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--portal-build', type=Path, default=REPO / 'apps/appliance-portal')
    parser.add_argument('--skip-portal-build', action='store_true', help='Use an existing portal build')
    parser.add_argument('--license-public-key', type=Path, default=KEYS / 'license-public.pem')
    parser.add_argument('--update-public-key', type=Path)
    parser.add_argument('--test-update-key', action='store_true')
    parser.add_argument('--minimum-version', default='0.1.1')
    parser.add_argument('--commit')
    args = parser.parse_args()

    commit = args.commit or run(['git', '-C', str(REPO), 'rev-parse', 'HEAD']).strip()
    out = args.output
    if out.exists() and any(out.iterdir()):
        raise ReleaseError('Output directory is not empty; use a new release directory')
    out.mkdir(parents=True, exist_ok=True)
    os.environ['SOURCE_DATE_EPOCH'] = source_date_epoch(commit)
    suffix = '-TEST' if args.test_update_key else ''
    public_update_key, private_update_key = update_key(args, out)
    if not args.skip_portal_build:
        build_portal(args.portal_build, commit)

    appliance = out / f'appliance-deployment-{args.version}{suffix}.zip'
    installer = out / f'bliss-mfa-windows-{args.version}{suffix}.zip'
    run([sys.executable, str(SCRIPTS / 'build-vm-package.py'), '--appliance', '--version', args.version,
         '--work-root', str(args.inputs / 'work'), '--input-directory', str(args.inputs / 'inputs'),
         '--portal-build', str(args.portal_build), '--node', str(args.inputs / 'node/node.exe'),
         '--license-public-key', str(args.license_public_key), '--update-public-key', str(public_update_key),
         '--output', str(appliance)])
    run([sys.executable, str(SCRIPTS / 'build-client-release.py'), '--archive', str(appliance),
         '--output', str(installer)])
    installer.with_suffix('.json').unlink(missing_ok=True)
    verification = verify_customer_artifacts(appliance, installer)

    update_record = None
    if private_update_key:
        update = out / f'bliss-mfa-update-{args.version}{suffix}.zip'
        run([sys.executable, str(SCRIPTS / 'publish-client-update.py'), '--appliance', str(appliance),
             '--output', str(update), '--key', str(private_update_key), '--version', args.version,
             '--minimum-version', args.minimum_version, '--url', TEST_UPDATE_URL.format(version=args.version)])
        report = json.loads(run([sys.executable, str(SCRIPTS / 'verify-pilot-release.py'), '--appliance', str(appliance),
                                 '--installer', str(installer), '--update', str(update),
                                 '--manifest', str(update.with_suffix('.signed.json')),
                                 '--public-key', str(public_update_key),
                                 '--current-version', args.minimum_version]))
        verification.update(report)
        update_record = {'filename': update.name, 'sha256': sha256(update), 'size': update.stat().st_size,
                         'signed_manifest': update.with_suffix('.signed.json').name}
    else:
        verification['verified'] = True
        verification['update'] = ('not built: sign offline with publish-client-update.py using the production key, '
                                  'URL ' + UPDATE_URL.format(version=args.version))

    record = {
        'product': 'bliss-mfa-windows', 'version': args.version, 'test_build': bool(suffix),
        'source_commit': commit, 'source_date_epoch': int(os.environ['SOURCE_DATE_EPOCH']),
        'inputs_manifest_sha256': sha256(REPO / 'deployment/windows/build-inputs.json'),
        'wheel_lock_sha256': sha256(REPO / 'deployment/windows/appliance-requirements.lock'),
        'license_public_key_sha256': sha256(args.license_public_key),
        'update_public_key_sha256': sha256(public_update_key),
        'appliance': {'filename': appliance.name, 'sha256': sha256(appliance), 'size': appliance.stat().st_size},
        'installer': {'filename': installer.name, 'sha256': sha256(installer), 'size': installer.stat().st_size},
        'update': update_record,
        'verification': verification,
        'code_signing': 'unsigned (no Authenticode certificate available to this build)',
    }
    (out / 'release.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    (out / (installer.name + '.sha256')).write_text(record['installer']['sha256'] + '  ' + installer.name + '\n')
    print(json.dumps({k: record[k] for k in ('version', 'test_build', 'source_commit', 'installer')}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except ReleaseError as error:
        print('Release build failed: ' + str(error), file=sys.stderr)
        raise SystemExit(2) from None
