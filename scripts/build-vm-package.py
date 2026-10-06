"""Build a secret-free Windows engine prototype package from this test kit.

Prerequisites under .local/deployment: python-embed.zip, wheels/*.whl,
vc_redist.x64.exe, provider/multiOTPCredentialProviderInstaller.msi.
Download artifacts from their official publishers and verify installer signatures.
"""
import argparse
import hashlib
import json
import os
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORK = REPO.parent
INPUT = REPO / '.local/deployment'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--appliance', action='store_true')
parser.add_argument('--portal-build', type=Path)
parser.add_argument('--node', type=Path)
parser.add_argument('--version', default='0.1.1')
parser.add_argument('--work-root', type=Path, default=WORK,
                    help='Directory containing multiotp-engine and php-runtime')
parser.add_argument('--input-directory', type=Path, default=INPUT,
                    help='Verified packaging runtimes, wheels and installers')
parser.add_argument('--license-public-key', type=Path,
                    default=REPO / '.local/hosted/license-public.pem')
parser.add_argument('--update-public-key', type=Path)
parser.add_argument('--output', type=Path,
                    help='New output ZIP; existing outputs are never overwritten')
args = parser.parse_args()
if args.appliance and (not args.portal_build or not args.node):
    parser.error('Appliance packaging requires --portal-build and --node')
WORK = args.work_root.resolve()
INPUT = args.input_directory.resolve()
OUTPUT = args.output or INPUT / ('appliance-deployment.zip' if args.appliance else 'engine-deployment.zip')
update_public_key = args.update_public_key or INPUT / 'update-public.pem'
required_files = [INPUT / 'python-embed.zip', INPUT / 'WinSW-x64.exe', INPUT / 'WINSW-LICENSE',
                  INPUT / 'vc_redist.x64.exe', INPUT / 'provider/multiOTPCredentialProviderInstaller.msi']
required_directories = [WORK / 'multiotp-engine/contrib', WORK / 'php-runtime']
for name in ('multiotp.php', 'multiotp.class.php', 'COPYING', 'COPYING.LESSER', 'README.md'):
    required_files.append(WORK / 'multiotp-engine' / name)
wheels_directory = INPUT / ('appliance-wheels' if args.appliance else 'wheels')
if not list(wheels_directory.glob('*.whl')):
    parser.error('Pinned packaging wheels are missing')
if args.appliance:
    import re
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
        parser.error('Version must be major.minor.patch')
    required_files += [args.node, INPUT / 'NODE-LICENSE', args.license_public_key, update_public_key,
                       args.portal_build / '.next/standalone/server.js']
    required_directories += [args.portal_build / '.next/static']
for path in required_files:
    if not path.is_file():
        parser.error('Packaging file missing: ' + str(path))
for path in required_directories:
    if not path.is_dir():
        parser.error('Packaging directory missing: ' + str(path))
if args.appliance:
    for path in (args.license_public_key, update_public_key):
        if not isinstance(serialization.load_pem_public_key(path.read_bytes()), Ed25519PublicKey):
            parser.error('Packaging public keys must be Ed25519')
    if args.license_public_key.read_bytes() == update_public_key.read_bytes():
        parser.error('License and update signing keys must be separate')
if OUTPUT.exists():
    parser.error('Output already exists; choose a new release path')
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
MANIFEST = {}
# Reproducible archives: a fixed entry timestamp (SOURCE_DATE_EPOCH convention) and mode.
ZIP_TIME = time.gmtime(int(os.environ.get('SOURCE_DATE_EPOCH', '315532800')))[:6]


def entry(name):
    info = zipfile.ZipInfo(name, ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def add(archive, name, data):
    if name in MANIFEST:
        raise RuntimeError('Duplicate archive path: ' + name)
    archive.writestr(entry(name), data)
    MANIFEST[name] = hashlib.sha256(data).hexdigest()


def tree(archive, source, prefix):
    for path in sorted(source.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            add(archive, prefix + '/' + path.relative_to(source).as_posix(), path.read_bytes())


with zipfile.ZipFile(OUTPUT, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
    with zipfile.ZipFile(INPUT / 'python-embed.zip') as python:
        for name in python.namelist():
            if not name.endswith('/') and name != 'python312._pth':
                add(archive, 'python/' + name, python.read(name))
    add(archive, 'python/python312._pth', b'python312.zip\n.\nLib/site-packages\n../bliss-mfa/services/multiotp-adapter\n../bliss-mfa/apps/appliance-api\n../bliss-mfa/services/license-agent\nimport site\n')
    wheels = INPUT / ('appliance-wheels' if args.appliance else 'wheels')
    for wheel in sorted(wheels.glob('*.whl')):
        with zipfile.ZipFile(wheel) as package:
            for name in package.namelist():
                if not name.endswith('/'):
                    add(archive, 'python/Lib/site-packages/' + name, package.read(name))
    sources = ['scripts/run-engine.py', 'scripts/engine_supervisor.py', 'deployment/engine-auth/router.php',
                     'scripts/Install-EngineService.ps1', 'scripts/engine-backup.py',
                     'scripts/appliance-runtime.py', 'scripts/Install-BlissEngine.ps1',
                     'scripts/Patch-ProviderHttpFraming.ps1', 'scripts/verify-native-cgi.py',
                     'scripts/Stage-BlissProvider.ps1', 'scripts/Enable-RdpProtection.ps1',
                     'scripts/provider-readiness.py']
    if not args.appliance:
        sources += [
                     'scripts/verify-vm-engine.py', 'scripts/verify-vm-runtime.py',
                     'scripts/render-prototype-enrollment.py',
                     'scripts/Recover-PrototypeProvider.ps1',
                     'scripts/Setup-PrototypeTestAccount.ps1',
                     'scripts/Test-PrototypeRestart.ps1',
                     'scripts/Install-PrototypeProvider.ps1',
                     'scripts/Install-PrototypeEngine.ps1',
                     'scripts/Patch-PrototypeProviderTrust.ps1',
                     'deployment/engine-auth/FIRST-DEPLOYMENT.md']
    for relative in sources:
        add(archive, 'bliss-mfa/' + relative, (REPO / relative).read_bytes())
    add(archive, 'installers/WinSW-x64.exe', (INPUT / 'WinSW-x64.exe').read_bytes())
    add(archive, 'installers/WINSW-LICENSE', (INPUT / 'WINSW-LICENSE').read_bytes())
    tree(archive, REPO / 'services/multiotp-adapter/adapter', 'bliss-mfa/services/multiotp-adapter/adapter')
    if args.appliance:
        add(archive, 'bliss-mfa/deployment/release-version.json', json.dumps({'version': args.version}).encode())
        for name in ('Install-WindowsIntegration.ps1', 'Uninstall-BlissMFA.ps1', 'Update-BlissMFA.ps1', 'client-update.py',
                     'Merge-ReinstallFiles.ps1'):
            add(archive, 'bliss-mfa/scripts/' + name, (REPO / 'scripts' / name).read_bytes())
        add(archive, 'bliss-mfa/deployment/update-public.pem', update_public_key.read_bytes())
        tree(archive, REPO / 'apps/appliance-api/appliance', 'bliss-mfa/apps/appliance-api/appliance')
        tree(archive, REPO / 'services/license-agent/license_agent', 'bliss-mfa/services/license-agent/license_agent')
        tree(archive, args.portal_build / '.next/standalone', 'portal')
        tree(archive, args.portal_build / '.next/static', 'portal/.next/static')
        add(archive, 'node/node.exe', args.node.read_bytes())
        add(archive, 'node/LICENSE', (INPUT / 'NODE-LICENSE').read_bytes())
        add(archive, 'bliss-mfa/deployment/license-public.pem',
            args.license_public_key.read_bytes())
    for name in ['multiotp.php', 'multiotp.class.php', 'COPYING', 'COPYING.LESSER', 'README.md']:
        add(archive, 'multiotp-engine/' + name, (WORK / 'multiotp-engine' / name).read_bytes())
    tree(archive, WORK / 'multiotp-engine/contrib', 'multiotp-engine/contrib')
    tree(archive, WORK / 'php-runtime', 'php-runtime')
    for source in [INPUT / 'vc_redist.x64.exe', INPUT / 'provider/multiOTPCredentialProviderInstaller.msi']:
        add(archive, 'installers/' + source.name, source.read_bytes())
    archive.writestr(entry('manifest.json'), json.dumps(MANIFEST, indent=2))
print(f'Built {OUTPUT} ({OUTPUT.stat().st_size} bytes, {len(MANIFEST)} files)')
print('SHA256: ' + hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
