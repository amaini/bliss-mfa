import importlib.util
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

spec = importlib.util.spec_from_file_location(
    "update_keys", Path(__file__).resolve().parents[1] / "generate-update-keys.py",
)
keys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(keys)


def test_provisioned_key_can_sign_and_is_never_replaced(tmp_path):
    directory = tmp_path / "signing"
    keys.provision(directory)
    private_bytes = (directory / "update-private.pem").read_bytes()
    public_bytes = (directory / "update-public.pem").read_bytes()
    private = serialization.load_pem_private_key(private_bytes, password=None)
    assert isinstance(private, Ed25519PrivateKey)
    public = serialization.load_pem_public_key(public_bytes)
    public.verify(private.sign(b"pilot manifest"), b"pilot manifest")
    with pytest.raises(FileExistsError):
        keys.provision(directory)
    assert (directory / "update-private.pem").read_bytes() == private_bytes
    assert (directory / "update-public.pem").read_bytes() == public_bytes


def test_partial_existing_key_is_preserved(tmp_path):
    directory = keys.secure_directory(tmp_path / "signing")
    private = directory / "update-private.pem"
    private.write_bytes(b"existing protected key")
    with pytest.raises(FileExistsError):
        keys.provision(directory)
    assert private.read_bytes() == b"existing protected key"
    assert not (directory / "update-public.pem").exists()
