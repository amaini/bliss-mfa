"""Provision a separate update key in a private directory; never overwrite keys."""
import argparse
import hashlib
import os
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def secure_directory(directory):
    directory = directory.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink():
        raise ValueError("Signing directory must not be a symbolic link")
    if os.name == "nt":
        script = """
$ErrorActionPreference = 'Stop'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
$acl.SetOwner($sid)
foreach ($identity in @($sid, (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))) {
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
[IO.Directory]::SetAccessControl($env:BLISS_UPDATE_KEY_DIRECTORY, $acl)
"""
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             script], env={**os.environ, "BLISS_UPDATE_KEY_DIRECTORY": str(directory)},
            check=True, capture_output=True, text=True,
        )
    else:
        directory.chmod(0o700)
    return directory


def provision(directory):
    directory = secure_directory(directory)
    private = directory / "update-private.pem"
    public = directory / "update-public.pem"
    if private.exists() or public.exists():
        raise FileExistsError("Signing key already exists; preserve it instead of rotating it")
    key = Ed25519PrivateKey.generate()
    # The directory ACL is applied before any private bytes are written.
    with private.open("xb") as stream:
        stream.write(key.private_bytes(serialization.Encoding.PEM,
                                      serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    if os.name != "nt":
        private.chmod(0o600)
    pem = key.public_key().public_bytes(serialization.Encoding.PEM,
                                      serialization.PublicFormat.SubjectPublicKeyInfo)
    with public.open("xb") as stream:
        stream.write(pem)
    print("Update signing key created in protected directory.")
    print("Public key SHA256: " + hashlib.sha256(pem).hexdigest())
    print("Keep a secure offline recovery copy of the private key before customer release.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    provision(parser.parse_args().directory)
