import hashlib
import importlib.util
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

spec = importlib.util.spec_from_file_location(
    "manager", Path(__file__).parents[1] / "manager.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Ops:
    def __init__(self, fail=False):
        self.events = []
        self.fail = fail

    def protect(self, root):
        self.events.append("protect")

    def stop(self, root):
        self.events.append("stop")

    def start(self, root):
        self.events.append("start")

    def install(self, root):
        self.events.append("install")

    def repair(self, root):
        self.events.append("repair")

    def ready(self, root):
        self.events.append("ready")
        if self.fail:
            self.fail = False
            # Simulate a migration made before a startup failure.
            (root / "bliss-mfa/.local/secret.txt").write_text("changed")
            raise RuntimeError("bad startup")


def bundle(tmp_path, monkeypatch, sequence=1):
    provider = b"fixture-provider"
    provider_hash = hashlib.sha256(provider).hexdigest()
    monkeypatch.setattr(m, "PROVIDER_HASH", provider_hash)
    metadata = {
        "product": "bliss-mfa-windows",
        "sequence": sequence,
        "version": f"0.2.{sequence}",
        "channel": "stable",
        "provider_sha256": provider_hash,
    }
    files = {f"{c}/fixture.txt": f"version-{sequence}".encode() for c in m.COMPONENTS}
    files["installers/multiOTPCredentialProviderInstaller.msi"] = provider
    files["bliss-mfa/deployment/update-public.pem"] = b"fixture-key"
    files["release.json"] = json.dumps(metadata).encode()
    path = tmp_path / f"release-{sequence}.zip"
    with zipfile.ZipFile(path, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
        z.writestr(
            "manifest.json",
            json.dumps({n: hashlib.sha256(v).hexdigest() for n, v in files.items()}),
        )
    return path, m.sha256(path)


def installed(tmp_path, monkeypatch):
    archive, digest = bundle(tmp_path, monkeypatch)
    root = tmp_path / "appliance"
    m.apply_archive(
        root, archive, digest, "install", Ops(), {"updates_url": "https://updates.test"}
    )
    (root / "bliss-mfa/.local/secret.txt").write_text("original-seed")
    return root, archive, digest


def test_install_creates_ready_identity_and_cached_repair(tmp_path, monkeypatch):
    root, archive, digest = installed(tmp_path, monkeypatch)
    identity = json.loads(
        (root / "bliss-mfa/.local/updater/installation.json").read_text()
    )
    assert identity["status"] == "ready"
    assert m.sha256(root / ".release-cache" / (digest + ".zip")) == digest


def test_update_preserves_seeds_and_uses_new_binaries(tmp_path, monkeypatch):
    root, _, _ = installed(tmp_path, monkeypatch)
    archive, digest = bundle(tmp_path, monkeypatch, 2)
    ops = Ops()
    result = m.apply_archive(root, archive, digest, "update", ops)
    assert result["sequence"] == 2
    assert (root / "python/fixture.txt").read_text() == "version-2"
    assert (root / "bliss-mfa/.local/secret.txt").read_text() == "original-seed"
    assert ops.events == ["protect", "stop", "start", "ready"]


def test_failed_startup_restores_binaries_identity_and_state(tmp_path, monkeypatch):
    root, _, _ = installed(tmp_path, monkeypatch)
    archive, digest = bundle(tmp_path, monkeypatch, 2)
    ops = Ops(fail=True)
    with pytest.raises(RuntimeError, match="bad startup"):
        m.apply_archive(root, archive, digest, "update", ops)
    assert (root / "python/fixture.txt").read_text() == "version-1"
    assert (root / "bliss-mfa/.local/secret.txt").read_text() == "original-seed"
    assert (
        json.loads((root / "bliss-mfa/.local/updater/installation.json").read_text())[
            "sequence"
        ]
        == 1
    )
    assert ops.events[-3:] == ["stop", "start", "ready"]


def test_repair_restores_damaged_file_without_reenrollment(tmp_path, monkeypatch):
    root, archive, digest = installed(tmp_path, monkeypatch)
    (root / "python/fixture.txt").unlink()
    m.apply_archive(root, archive, digest, "repair", Ops())
    assert (root / "python/fixture.txt").read_text() == "version-1"
    assert (root / "bliss-mfa/.local/secret.txt").read_text() == "original-seed"


def test_interrupted_update_recovers_previous_binary_and_identity(
    tmp_path, monkeypatch
):
    root, _, _ = installed(tmp_path, monkeypatch)
    archive, digest = bundle(tmp_path, monkeypatch, 2)

    class Crash(Ops):
        def ready(self, root):
            raise KeyboardInterrupt("simulate interrupted updater")

    with pytest.raises(KeyboardInterrupt):
        m.apply_archive(root, archive, digest, "update", Crash())
    assert (root / "python/fixture.txt").read_text() == "version-2"
    assert list(root.glob(".bliss-transaction-*/journal.json"))
    m.recover_interrupted(root, Ops())
    assert (root / "python/fixture.txt").read_text() == "version-1"
    assert (root / "bliss-mfa/.local/secret.txt").read_text() == "original-seed"
    assert not list(root.glob(".bliss-transaction-*"))


def test_wrong_repair_release_and_downgrade_do_not_stop_service(tmp_path, monkeypatch):
    root, original, digest = installed(tmp_path, monkeypatch)
    newer, new_digest = bundle(tmp_path, monkeypatch, 2)
    ops = Ops()
    with pytest.raises(ValueError, match="exact installed"):
        m.apply_archive(root, newer, new_digest, "repair", ops)
    with pytest.raises(ValueError, match="Downgrade"):
        m.apply_archive(root, original, digest, "update", ops)
    assert "stop" not in ops.events


def test_bad_archive_hash_does_not_stop_service(tmp_path, monkeypatch):
    root, archive, _ = installed(tmp_path, monkeypatch)
    ops = Ops()
    with pytest.raises(ValueError, match="checksum"):
        m.apply_archive(root, archive, "0" * 64, "repair", ops)
    assert "stop" not in ops.events


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "python/../../escape",
        "C:/escape",
        "python\\escape",
        "python/CON",
        "python/a.",
        "bliss-mfa/.local/key",
        "service/owned.exe",
    ],
)
def test_unsafe_release_paths(name):
    with pytest.raises(ValueError):
        m.safe_member(name)


def test_signature_expiry_channel_downgrade_and_provider_validation(tmp_path):
    key = Ed25519PrivateKey.generate()
    public = tmp_path / "public.pem"
    public.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    now = datetime.now(UTC)
    descriptor = {
        "schema": 1,
        "product": "bliss-mfa-windows",
        "channel": "stable",
        "version": "0.2.0",
        "sequence": 2,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "sha256": "a" * 64,
        "size": 100,
        "archive_url": "https://releases.test/release.zip",
        "provider_sha256": m.PROVIDER_HASH,
    }

    def sign(d):
        body = m.canonical(d)
        return {"payload": m.encode(body), "signature": m.encode(key.sign(body))}

    valid = sign(descriptor)
    assert m.verified_descriptor(valid, public, 1, "stable")["sequence"] == 2
    with pytest.raises(ValueError):
        m.verified_descriptor(valid, public, 2, "stable")
    with pytest.raises(ValueError):
        m.verified_descriptor(valid, public, 1, "preview")
    with pytest.raises(ValueError):
        m.verified_descriptor(valid, public, 1, "stable", now + timedelta(hours=1))
    with pytest.raises(ValueError):
        m.verified_descriptor(
            sign({**descriptor, "provider_sha256": "0" * 64}), public, 1, "stable"
        )
    with pytest.raises(InvalidSignature):
        m.verified_descriptor(
            {**valid, "payload": m.encode(m.canonical({**descriptor, "sequence": 3}))},
            public,
            1,
            "stable",
        )
