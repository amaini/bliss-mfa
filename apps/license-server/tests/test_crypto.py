from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_server.config import get_settings
from license_server.crypto import sign_payload


def test_sign_payload(monkeypatch):
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    monkeypatch.setenv("SIGNING_PRIVATE_KEY_PEM", pem)
    get_settings.cache_clear()

    token = sign_payload({"license_id": "lic_test", "max_rdp_users": 25})
    assert isinstance(token, str)
    assert len(token) > 40
