"""Build a secret-free Windows engine prototype package from this test kit.

Prerequisites under .local/deployment: python-embed.zip, wheels/*.whl,
vc_redist.x64.exe, provider/multiOTPCredentialProviderInstaller.msi.
Download artifacts from their official publishers and verify installer signatures.
"""
import hashlib
import json
from pathlib import Path
import zipfile

REPO = Path(__file__).resolve().parents[1]
WORK = REPO.parent
INPUT = REPO / '.local/deployment'
OUTPUT = INPUT / 'engine-deployment.zip'
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
    add(archive, 'python/python312._pth', b'python312.zip\n.\nLib/site-packages\n../bliss-mfa/services/multiotp-adapter\nimport site\n')
    for wheel in sorted((INPUT / 'wheels').glob('*.whl')):
        with zipfile.ZipFile(wheel) as package:
            for name in package.namelist():
                if not name.endswith('/'):
                    add(archive, 'python/Lib/site-packages/' + name, package.read(name))
    for relative in ['scripts/run-engine.py', 'deployment/engine-auth/router.php',
                     'scripts/verify-vm-engine.py', 'scripts/verify-vm-runtime.py',
                     'scripts/render-prototype-enrollment.py',
                     'scripts/Recover-PrototypeProvider.ps1',
                     'scripts/Setup-PrototypeTestAccount.ps1',
                     'scripts/Test-PrototypeRestart.ps1',
                     'scripts/Install-PrototypeProvider.ps1',
                     'scripts/Install-PrototypeEngine.ps1',
                     'scripts/Patch-PrototypeProviderTrust.ps1',
                     'deployment/engine-auth/FIRST-DEPLOYMENT.md']:
        add(archive, 'bliss-mfa/' + relative, (REPO / relative).read_bytes())
    tree(archive, REPO / 'services/multiotp-adapter/adapter', 'bliss-mfa/services/multiotp-adapter/adapter')
    for name in ['multiotp.php', 'multiotp.class.php', 'COPYING', 'COPYING.LESSER', 'README.md']:
        add(archive, 'multiotp-engine/' + name, (WORK / 'multiotp-engine' / name).read_bytes())
    tree(archive, WORK / 'multiotp-engine/contrib', 'multiotp-engine/contrib')
    tree(archive, WORK / 'php-runtime', 'php-runtime')
    for source in [INPUT / 'vc_redist.x64.exe', INPUT / 'provider/multiOTPCredentialProviderInstaller.msi']:
        add(archive, 'installers/' + source.name, source.read_bytes())
    archive.writestr('manifest.json', json.dumps(MANIFEST, indent=2))
print(f'Built {OUTPUT} ({OUTPUT.stat().st_size} bytes, {len(MANIFEST)} files)')
