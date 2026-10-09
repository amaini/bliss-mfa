import hashlib
import importlib.util
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

spec = importlib.util.spec_from_file_location(
    "backup_update_key", Path(__file__).resolve().parents[1] / "backup-update-key.py",
)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)

PASSPHRASE = "correct horse battery staple 42"


def signing_key(tmp_path):
    key = Ed25519PrivateKey.generate()
    private = tmp_path / "signing" / "update-private.pem"
    private.parent.mkdir()
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    public_pem = key.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    return key, private, hashlib.sha256(public_pem).hexdigest()


def test_backup_is_encrypted_and_restores_the_same_key(tmp_path):
    key, private, fingerprint = signing_key(tmp_path)
    written = backup.backup(private, [tmp_path / "usb", tmp_path / "vault"], PASSPHRASE, fingerprint)
    assert len(written) == 2
    for path in written:
        data = path.read_bytes()
        assert b"ENCRYPTED PRIVATE KEY" in data
        with pytest.raises(TypeError):
            serialization.load_pem_private_key(data, password=None)
        restored = serialization.load_pem_private_key(data, password=PASSPHRASE.encode())
        restored.public_key().verify(restored.sign(b"manifest"), b"manifest")
        assert restored.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw) == \
            key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        assert fingerprint in (path.parent / backup.README_NAME).read_text()


def test_wrong_passphrase_cannot_restore(tmp_path):
    _, private, fingerprint = signing_key(tmp_path)
    [path] = backup.backup(private, [tmp_path / "usb"], PASSPHRASE, fingerprint)
    with pytest.raises(ValueError):
        serialization.load_pem_private_key(path.read_bytes(), password=b"not the passphrase at all")


def test_refuses_a_key_that_does_not_match_the_expected_fingerprint(tmp_path):
    _, private, _ = signing_key(tmp_path)
    with pytest.raises(ValueError, match="fingerprint"):
        backup.backup(private, [tmp_path / "usb"], PASSPHRASE, "0" * 64)
    assert not (tmp_path / "usb").exists()


def test_refuses_short_passphrase(tmp_path):
    _, private, fingerprint = signing_key(tmp_path)
    with pytest.raises(ValueError, match="16"):
        backup.backup(private, [tmp_path / "usb"], "short", fingerprint)


def test_never_overwrites_an_existing_backup(tmp_path):
    _, private, fingerprint = signing_key(tmp_path)
    [path] = backup.backup(private, [tmp_path / "usb"], PASSPHRASE, fingerprint)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        backup.backup(private, [tmp_path / "usb"], PASSPHRASE, fingerprint)
    assert path.read_bytes() == before


def test_refuses_destination_inside_the_signing_directory(tmp_path):
    _, private, fingerprint = signing_key(tmp_path)
    with pytest.raises(ValueError, match="separate"):
        backup.backup(private, [private.parent / "copy"], PASSPHRASE, fingerprint)
