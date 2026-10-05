"""Exercise actual package creation with isolated non-executable runtime fixtures."""
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SCRIPT = Path(__file__).resolve().parents[1] / "build-vm-package.py"


@pytest.fixture
def packaging(tmp_path):
    work = tmp_path / "work"
    inputs = tmp_path / "inputs"
    portal = tmp_path / "portal"
    files = [inputs / "WinSW-x64.exe", inputs / "WINSW-LICENSE", inputs / "vc_redist.x64.exe",
             inputs / "provider/multiOTPCredentialProviderInstaller.msi", inputs / "NODE-LICENSE",
             tmp_path / "node.exe", portal / ".next/standalone/server.js",
             portal / ".next/static/fixture.js", work / "php-runtime/php.exe",
             work / "multiotp-engine/contrib/fixture.php"]
    files += [work / "multiotp-engine" / name for name in
              ("multiotp.php", "multiotp.class.php", "COPYING", "COPYING.LESSER", "README.md")]
    for file in files:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"non-executable packaging fixture")
    with zipfile.ZipFile(inputs / "python-embed.zip", "w") as archive:
        archive.writestr("python.exe", b"fixture")
    wheels = inputs / "appliance-wheels"
    wheels.mkdir()
    with zipfile.ZipFile(wheels / "fixture.whl", "w") as archive:
        archive.writestr("fixture/__init__.py", b"")
    for name in ("license-public.pem", "update-public.pem"):
        (inputs / name).write_bytes(Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    output = tmp_path / "release.zip"
    command = [sys.executable, str(SCRIPT), "--appliance", "--work-root", str(work),
               "--input-directory", str(inputs), "--portal-build", str(portal),
               "--node", str(tmp_path / "node.exe"), "--license-public-key",
               str(inputs / "license-public.pem"), "--output", str(output), "--version", "0.1.2"]
    return command, inputs, output


def test_package_from_separate_checkout_preserves_existing_release(packaging):
    import hashlib
    import json

    command, _, output = packaging
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    before = output.read_bytes()
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert "bliss-mfa/apps/appliance-api/appliance/migrate.py" in names
        assert "bliss-mfa/deployment/update-public.pem" in names
        assert not any(".local/" in name or "private.pem" in name for name in names)
        manifest = json.loads(archive.read("manifest.json"))
        assert set(manifest) == set(names) - {"manifest.json"}
        assert all(hashlib.sha256(archive.read(name)).hexdigest() == digest
                   for name, digest in manifest.items())
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert output.read_bytes() == before


@pytest.mark.parametrize("problem", ["missing-key", "same-key", "private-key", "missing-runtime"])
def test_packaging_preflight_leaves_no_partial_release(packaging, problem):
    command, inputs, output = packaging
    if problem == "missing-key":
        (inputs / "update-public.pem").unlink()
    elif problem == "same-key":
        (inputs / "update-public.pem").write_bytes((inputs / "license-public.pem").read_bytes())
    elif problem == "private-key":
        (inputs / "update-public.pem").write_bytes(Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
    else:
        (inputs / "WinSW-x64.exe").unlink()
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert not output.exists()
