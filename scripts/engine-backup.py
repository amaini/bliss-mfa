"""Encrypted offline engine snapshots. Stop the engine before backup or restore.

Restore always creates a new directory; it never overwrites live engine state.
Keep the passphrase separately from the backup. Secrets never enter arguments.
"""

import argparse
import base64
import getpass
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"BLISSMFA-BACKUP-1\n"
MAX_BYTES = 256 * 1024 * 1024


def cipher(password, salt):
    if len(password) < 12:
        raise ValueError("Use a backup passphrase of at least 12 characters")
    key = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600000
    ).derive(password.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def backup(source: Path, output: Path, password: str):
    source = source.resolve()
    config = json.loads((source / "config.json").read_text(encoding="utf-8-sig"))
    # A relocated/custom state layout must be explicitly brought into this snapshot root.
    for key in ("state_dir", "certificate_file", "certificate_key_file"):
        if not Path(config[key]).resolve().is_relative_to(source):
            raise ValueError(
                "Engine state and certificate must be inside the snapshot root"
            )
    data = io.BytesIO()
    manifest = {}
    total = 0
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        if any(
            (source / name).exists()
            for name in ("backup-layout.json", "backup-manifest.json")
        ):
            raise ValueError("Snapshot contains a reserved metadata file")
        for path in sorted(source.rglob("*")):
            if path.is_symlink() or path.is_junction():
                raise ValueError("Snapshot contains a symbolic link or junction")
            if not path.is_file() or path.suffix in {".log", ".stop"}:
                continue
            content = path.read_bytes()
            total += len(content)
            if total > MAX_BYTES:
                raise ValueError("Snapshot exceeds supported size")
            name = path.relative_to(source).as_posix()
            manifest[name] = hashlib.sha256(content).hexdigest()
            archive.writestr(name, content)
        layout = json.dumps({"snapshot_root": str(source)}).encode("utf-8")
        manifest["backup-layout.json"] = hashlib.sha256(layout).hexdigest()
        archive.writestr("backup-layout.json", layout)
        archive.writestr("backup-manifest.json", json.dumps(manifest, sort_keys=True))
    salt = os.urandom(16)
    encrypted = MAGIC + salt + cipher(password, salt).encrypt(data.getvalue())
    # Exclusive creation protects earlier recovery points.
    with output.open("xb") as stream:
        stream.write(encrypted)
    return len(manifest)


def restore(backup_file: Path, destination: Path, password: str):
    if destination.exists():
        raise ValueError("Restore destination already exists")
    if backup_file.stat().st_size > MAX_BYTES * 2:
        raise ValueError("Backup exceeds supported size")
    data = backup_file.read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError("Unsupported backup format")
    salt = data[len(MAGIC) : len(MAGIC) + 16]
    try:
        payload = cipher(password, salt).decrypt(data[len(MAGIC) + 16 :])
    except InvalidToken:
        raise ValueError("Incorrect passphrase or damaged backup") from None
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bliss-restore-", dir=destination.parent))
    try:
        if os.name == "nt":
            account = subprocess.check_output(["whoami.exe"], text=True).strip()
            subprocess.run(
                [
                    "icacls.exe",
                    str(stage),
                    "/inheritance:r",
                    "/grant:r",
                    "*S-1-5-18:(OI)(CI)F",
                    "*S-1-5-32-544:(OI)(CI)F",
                    account + ":(OI)(CI)F",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            if (
                len(names) != len({name.casefold() for name in names})
                or sum(i.file_size for i in archive.infolist()) > MAX_BYTES
            ):
                raise ValueError("Invalid backup contents")
            manifest = json.loads(archive.read("backup-manifest.json"))
            if set(names) != set(manifest) | {"backup-manifest.json"}:
                raise ValueError("Backup manifest mismatch")
            for name, digest in manifest.items():
                relative = PurePosixPath(name)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or "\\" in name
                    or ":" in name
                ):
                    raise ValueError("Unsafe backup path")
                target = stage.joinpath(*relative.parts)
                if not target.resolve().is_relative_to(stage):
                    raise ValueError("Unsafe backup path")
                content = archive.read(name)
                if hashlib.sha256(content).hexdigest() != digest:
                    raise ValueError("Backup integrity mismatch")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        config_path = stage / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        layout_path = stage / "backup-layout.json"
        old_root = (
            Path(json.loads(layout_path.read_text())["snapshot_root"])
            if layout_path.exists()
            else Path(config["certificate_file"]).parent
        )
        for key in ("state_dir", "certificate_file", "certificate_key_file"):
            relative = Path(config[key]).relative_to(old_root)
            config[key] = str(destination / relative)
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        appliance_path = stage / "appliance.json"
        if appliance_path.exists():
            appliance = json.loads(appliance_path.read_text(encoding="utf-8-sig"))
            for key in ("database_file", "license_state_dir", "public_key_file"):
                relative = Path(appliance[key]).relative_to(old_root)
                appliance[key] = str(destination / relative)
            appliance_path.write_text(json.dumps(appliance, indent=2), encoding="utf-8")
        layout_path.unlink(missing_ok=True)
        stage.rename(destination)
        return len(manifest)
    finally:
        if stage.exists():
            if not stage.resolve().is_relative_to(destination.parent.resolve()):
                raise ValueError("Restore staging directory escaped its parent")
            shutil.rmtree(stage)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "restore"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument(
        "--password-file",
        type=Path,
        help="Private UTF-8 passphrase file; otherwise prompt",
    )
    parser.add_argument("--engine-stopped", action="store_true", required=True)
    args = parser.parse_args()
    password = (
        args.password_file.read_text(encoding="utf-8-sig").rstrip("\r\n")
        if args.password_file
        else getpass.getpass("Backup passphrase: ")
    )
    try:
        count = (backup if args.operation == "backup" else restore)(
            args.source, args.destination, password
        )
        print(f"{args.operation.capitalize()} verified: {count} files")
    except (ValueError, OSError, zipfile.BadZipFile):
        raise SystemExit(
            "Backup operation failed; verify paths, passphrase, format, and available space"
        ) from None
