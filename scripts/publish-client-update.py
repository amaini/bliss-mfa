"""Build an application-only ZIP and an offline Ed25519-signed release feed."""
import argparse
import base64
import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

spec = importlib.util.spec_from_file_location('client_update', Path(__file__).with_name('client-update.py'))
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--appliance', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True, help='Offline private UPDATE signing key; not the licensing key')
    parser.add_argument('--version', required=True)
    parser.add_argument('--minimum-version', default='0.1.1')
    parser.add_argument('--url', required=True, help='HTTPS URL of the published application ZIP')
    args = parser.parse_args()
    updater.version(args.version)
    updater.version(args.minimum_version)
    updater.https(args.url)
    key = serialization.load_pem_private_key(args.key.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError('Update signing key must be Ed25519')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.appliance) as appliance, zipfile.ZipFile(args.output, 'x', zipfile.ZIP_DEFLATED) as update:
        for name in appliance.namelist():
            if name.startswith(('bliss-mfa/', 'portal/')) and not name.endswith('/'):
                updater.safe_name(name)
                update.writestr(name, appliance.read(name))
    with args.output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    release = {'format': 1, 'product': 'bliss-mfa-windows', 'version': args.version,
               'minimum_version': args.minimum_version, 'url': args.url,
               'sha256': digest, 'size': args.output.stat().st_size}
    payload = json.dumps(release, sort_keys=True, separators=(',', ':')).encode()
    envelope = {'payload': base64.b64encode(payload).decode(), 'signature': base64.b64encode(key.sign(payload)).decode()}
    args.output.with_suffix('.signed.json').write_text(json.dumps(envelope, indent=2))
    print('Built signed update ' + args.version + '. Publish ZIP first, then replace stable.json.')


if __name__ == '__main__':
    main()
