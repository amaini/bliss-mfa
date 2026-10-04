"""Verify installer and signed update artifacts without displaying private values."""
import argparse
import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from dotenv import dotenv_values


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(args):
    spec = importlib.util.spec_from_file_location("client_update", Path(__file__).with_name("client-update.py"))
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
    private_values = []
    if args.private_env:
        for name, value in dotenv_values(args.private_env).items():
            if value and len(value) >= 8 and any(
                part in name.upper() for part in ("SECRET", "PASSWORD", "TOKEN", "API_KEY")
            ):
                private_values.append(value.encode())
    if args.vm_config:
        config = json.loads(args.vm_config.read_text(encoding="utf-8-sig"))
        if config.get("password"):
            password = config["password"].encode()
            # Short fixture passwords can occur incidentally inside binaries.
            # Check their quoted literals rather than treating every substring
            # of a runtime DLL as an exposed Windows credential.
            if len(password) >= 8:
                private_values.append(password)
            else:
                private_values.extend((b'"' + password + b'"', b"'" + password + b"'"))

    def safe(name, data):
        if ".local" in Path(name).parts or name.endswith((".env", "private.pem", ".key")):
            raise ValueError("Private release path: " + name)
        if any(value in data for value in private_values):
            raise ValueError("Configured private value found in release file: " + name)
        if name.endswith(".pem"):
            if b"PRIVATE KEY-----" in data:
                raise ValueError("Private PEM found in release: " + name)
            if name.endswith("public.pem"):
                key = serialization.load_pem_public_key(data)
                if not isinstance(key, Ed25519PublicKey):
                    raise ValueError("Unexpected release public key")
            elif not x509.load_pem_x509_certificates(data):
                raise ValueError("Unexpected PEM in release: " + name)

    with zipfile.ZipFile(args.appliance) as archive:
        names = archive.namelist()
        if len(names) != len(set(name.lower() for name in names)):
            raise ValueError("Duplicate appliance paths")
        manifest = json.loads(archive.read("manifest.json"))
        if set(manifest) != set(names) - {"manifest.json"}:
            raise ValueError("Appliance manifest does not cover all files")
        for name, expected in manifest.items():
            data = archive.read(name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("Appliance file hash mismatch: " + name)
            safe(name, data)
        pinned = archive.read("bliss-mfa/deployment/update-public.pem")
        if pinned != args.public_key.read_bytes():
            raise ValueError("Appliance pins a different update key")
        source_version = json.loads(archive.read("bliss-mfa/deployment/release-version.json"))["version"]
    appliance_hash = digest(args.appliance)
    with zipfile.ZipFile(args.installer) as archive:
        with archive.open("BlissMFA-Appliance.zip") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != appliance_hash:
                raise ValueError("Customer installer embeds a different appliance")
        for name in archive.namelist():
            if name != "BlissMFA-Appliance.zip":
                safe(name, archive.read(name))
        if appliance_hash.encode() not in archive.read("Setup-BlissMFA.ps1"):
            raise ValueError("Customer setup does not pin the appliance hash")
    release = updater.verify_manifest(json.loads(args.manifest.read_text()), pinned, args.current_version)
    if release["version"] != source_version:
        raise ValueError("Application and signed release versions differ")
    if release["sha256"] != digest(args.update) or release["size"] != args.update.stat().st_size:
        raise ValueError("Signed update checksum or size differs")
    with zipfile.ZipFile(args.update) as update, zipfile.ZipFile(args.appliance) as appliance:
        expected = {name for name in appliance.namelist() if name.startswith(("bliss-mfa/", "portal/"))}
        if set(update.namelist()) != expected or len(update.namelist()) != len(expected):
            raise ValueError("Update contents differ from appliance application")
        for name in update.namelist():
            updater.safe_name(name)
            data = update.read(name)
            if data != appliance.read(name):
                raise ValueError("Update file differs from appliance: " + name)
            safe(name, data)
    result = {"version": source_version, "verified": True,
              "appliance_sha256": appliance_hash, "installer_sha256": digest(args.installer),
              "update_sha256": release["sha256"], "update_url": release["url"],
              "appliance_files": len(manifest), "update_files": len(expected),
              "private_values_checked": len(private_values),
              "vm_acceptance": "pending", "published": False}
    if args.output:
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("appliance", "installer", "update", "manifest", "public-key"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--current-version", default="0.1.1")
    parser.add_argument("--private-env", type=Path)
    parser.add_argument("--vm-config", type=Path)
    parser.add_argument("--output", type=Path)
    verify(parser.parse_args())
