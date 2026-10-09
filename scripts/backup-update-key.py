"""Write passphrase-encrypted recovery copies of the update signing key; never prints key material.

Each copy is an encrypted PKCS#8 PEM (restorable with this repository or plain OpenSSL), written
next to a README that records the public-key fingerprint and the restore command. Every copy is
decrypted again and checked against the expected fingerprint before the command reports success.

    python scripts/backup-update-key.py --key PRIVATE_KEY_PATH --destination E:\\ --destination F:\\bliss
"""
import argparse
import getpass
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO = Path(__file__).resolve().parents[1]
README_NAME = "README-update-key-backup.txt"
MIN_PASSPHRASE = 16


def fingerprint(key):
    pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(pem).hexdigest()


def backup(private_path, destinations, passphrase, expected_fingerprint):
    private_path = Path(private_path).resolve()
    if len(passphrase) < MIN_PASSPHRASE:
        raise ValueError(f"Use a passphrase of at least {MIN_PASSPHRASE} characters")
    key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("Update signing key must be Ed25519")
    actual = fingerprint(key)
    if actual != expected_fingerprint.lower():
        raise ValueError("Key fingerprint " + actual + " does not match the expected " + expected_fingerprint)
    encrypted = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.BestAvailableEncryption(passphrase.encode()))
    check = serialization.load_pem_private_key(encrypted, password=passphrase.encode())
    if fingerprint(check) != actual:
        raise RuntimeError("Encrypted copy did not decrypt to the same key")
    name = f"update-private-{actual[:8]}.pem.enc"
    targets = []
    for destination in destinations:
        destination = Path(destination).resolve()
        if destination == private_path.parent or private_path.parent in destination.parents:
            raise ValueError("Store backups in a separate location, not inside the signing directory")
        if (destination / name).exists() or (destination / README_NAME).exists():
            raise FileExistsError(f"A backup already exists in {destination}; keep it or choose another location")
        targets.append(destination)
    readme = (
        "Bliss MFA update signing key: encrypted recovery copy\n\n"
        f"File: {name}\n"
        f"Public key SHA-256: {actual}\n"
        "Encryption: PKCS#8 (PBES2), passphrase kept separately from this file.\n\n"
        "Restore into an access-restricted directory, then sign updates with publish-client-update.py:\n"
        f"  openssl pkey -in {name} -out update-private.pem\n"
        "  (or load it with Python cryptography using the passphrase)\n"
        "Check: the public key derived from the restored file must have the SHA-256 above\n"
        "(deployment/windows/keys/update-public.pem in the Bliss repository).\n"
    )
    written = []
    for destination in targets:
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / name
        with path.open("xb") as stream:
            stream.write(encrypted)
        with (destination / README_NAME).open("x", encoding="utf-8") as stream:
            stream.write(readme)
        reread = serialization.load_pem_private_key(path.read_bytes(), password=passphrase.encode())
        if fingerprint(reread) != actual:
            raise RuntimeError(f"Backup verification failed for {path}")
        written.append(path)
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key", type=Path, required=True, help="Unencrypted private update key (update-private.pem)")
    parser.add_argument("--destination", type=Path, action="append", required=True,
                        help="Backup folder; repeat for each copy (e.g. a USB drive)")
    parser.add_argument("--expected-public-key", type=Path, default=REPO / "deployment/windows/keys/update-public.pem")
    args = parser.parse_args()
    expected = hashlib.sha256(args.expected_public_key.read_bytes()).hexdigest()
    passphrase = getpass.getpass("Backup passphrase (16+ characters, store it separately): ")
    if getpass.getpass("Repeat passphrase: ") != passphrase:
        raise SystemExit("Passphrases differ; nothing was written.")
    for path in backup(args.key, args.destination, passphrase, expected):
        print("Verified encrypted backup: " + str(path))
    print("Public key SHA-256: " + expected)
    print("Keep the passphrase in your password manager, never next to these files.")


if __name__ == "__main__":
    main()
