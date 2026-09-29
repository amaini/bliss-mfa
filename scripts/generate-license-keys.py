#!/usr/bin/env python3
"""Generate Bliss license signing keys for a development or new environment.

The private key belongs only on Bliss licensing infrastructure.
Customer appliances receive only the public key.
"""

from pathlib import Path
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else ".local/license-keys")
    output.mkdir(parents=True, exist_ok=True)
    private_path = output / "license-private.pem"
    public_path = output / "license-public.pem"

    if private_path.exists() or public_path.exists():
        print(f"Refusing to overwrite existing keys in {output}")
        return 2

    key = Ed25519PrivateKey.generate()
    private_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    private_path.chmod(0o600)
    public_path.chmod(0o644)

    print(f"Private key: {private_path}")
    print(f"Public key:  {public_path}")
    print("Never copy the private key to a customer appliance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
