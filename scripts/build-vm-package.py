"""Build a secret-free Windows engine prototype package from this test kit.

Prerequisites under .local/deployment: python-embed.zip, wheels/*.whl,
vc_redist.x64.exe, provider/multiOTPCredentialProviderInstaller.msi.
Download artifacts from their official publishers and verify installer signatures.
"""
import argparse
import hashlib
import json
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
args = parser.parse_args()
if args.appliance and (not args.portal_build or not args.node):
    parser.error('Appliance packaging requires --portal-build and --node')
OUTPUT = INPUT / ('appliance-deployment.zip' if args.appliance else 'engine-deployment.zip')
MANIFEST = {}


def add(archive, name, data):
    if name in MANIFEST:
        raise RuntimeError('Duplicate archive path: ' + name)
    archive.writestr(name, data)
    MANIFEST[name] = hashlib.sha256(data).hexdigest()


def tree(archive, source, prefix):
    for path in sorted(source.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            add(archive, prefix + '/' + path.relative_to(source).as_posix(), path.read_bytes())


with zipfile.ZipFile(OUTPUT, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
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
    sources = ['scripts/run-engine.py', 'deployment/engine-auth/router.php',
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
        import re
        if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
            raise ValueError('Version must be major.minor.patch')
        add(archive, 'bliss-mfa/deployment/release-version.json', json.dumps({'version': args.version}).encode())
        for name in ('Install-WindowsIntegration.ps1', 'Uninstall-BlissMFA.ps1', 'Update-BlissMFA.ps1', 'client-update.py'):
            add(archive, 'bliss-mfa/scripts/' + name, (REPO / 'scripts' / name).read_bytes())
        add(archive, 'bliss-mfa/deployment/update-public.pem', (INPUT / 'update-public.pem').read_bytes())
        tree(archive, REPO / 'apps/appliance-api/appliance', 'bliss-mfa/apps/appliance-api/appliance')
        tree(archive, REPO / 'services/license-agent/license_agent', 'bliss-mfa/services/license-agent/license_agent')
        tree(archive, args.portal_build / '.next/standalone', 'portal')
        tree(archive, args.portal_build / '.next/static', 'portal/.next/static')
        add(archive, 'node/node.exe', args.node.read_bytes())
        add(archive, 'node/LICENSE', (INPUT / 'NODE-LICENSE').read_bytes())
        add(archive, 'bliss-mfa/deployment/license-public.pem',
            (REPO / '.local/hosted/license-public.pem').read_bytes())
    for name in ['multiotp.php', 'multiotp.class.php', 'COPYING', 'COPYING.LESSER', 'README.md']:
        add(archive, 'multiotp-engine/' + name, (WORK / 'multiotp-engine' / name).read_bytes())
    tree(archive, WORK / 'multiotp-engine/contrib', 'multiotp-engine/contrib')
    tree(archive, WORK / 'php-runtime', 'php-runtime')
    for source in [INPUT / 'vc_redist.x64.exe', INPUT / 'provider/multiOTPCredentialProviderInstaller.msi']:
        add(archive, 'installers/' + source.name, source.read_bytes())
    archive.writestr('manifest.json', json.dumps(MANIFEST, indent=2))
print(f'Built {OUTPUT} ({OUTPUT.stat().st_size} bytes, {len(MANIFEST)} files)')
print('SHA256: ' + hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
