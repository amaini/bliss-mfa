"""Verified Windows appliance install/repair/update transactions.

The control runtime lives outside the appliance being replaced. Platform operations
are isolated behind WindowsOps so transactions can be tested without host changes.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

COMPONENTS = {
    "python",
    "node",
    "portal",
    "php-runtime",
    "multiotp-engine",
    "bliss-mfa",
    "installers",
}
MAX_ARCHIVE = 2_000_000_000
MAX_EXPANDED = 6_000_000_000
PROVIDER_HASH = "21fe0897c0056cfadd9fc741affb77c0cc7c87c86022a51a7cb9f7ab1c65cbd5"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def encode(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def https_url(value):
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.fragment
    ):
        raise ValueError("HTTPS URL required without embedded credentials")
    return value


def verified_descriptor(envelope, public_key, current_sequence, channel, now=None):
    key = serialization.load_pem_public_key(Path(public_key).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Update key must be Ed25519")
    body = decode(envelope["payload"])
    if len(body) > 16_384:
        raise ValueError("Release descriptor exceeds limit")
    key.verify(decode(envelope["signature"]), body)
    descriptor = json.loads(body)
    now = now or datetime.now(UTC)
    expiry = datetime.fromisoformat(descriptor["expires_at"])
    issued = datetime.fromisoformat(descriptor["issued_at"])
    if (
        issued.tzinfo is None
        or expiry.tzinfo is None
        or issued.timestamp() > now.timestamp() + 300
        or expiry <= now
    ):
        raise ValueError("Release manifest expired or issued in the future")
    if (
        descriptor.get("schema") != 1
        or descriptor.get("product") != "bliss-mfa-windows"
    ):
        raise ValueError("Wrong release product/schema")
    if descriptor["channel"] != channel or descriptor["sequence"] <= current_sequence:
        raise ValueError("Release is not a newer version for this channel")
    if not re.fullmatch(r"\d+\.\d+\.\d+", descriptor["version"]):
        raise ValueError("Invalid release version")
    if (
        not re.fullmatch(r"[a-f0-9]{64}", descriptor["sha256"])
        or not 0 < descriptor["size"] <= MAX_ARCHIVE
    ):
        raise ValueError("Invalid release size/checksum")
    if descriptor["provider_sha256"] != PROVIDER_HASH:
        raise ValueError(
            "Credential-provider changes require a separately validated installer"
        )
    https_url(descriptor["archive_url"])
    return descriptor


def safe_member(name):
    if "\\" in name or ":" in name or name.startswith("/"):
        raise ValueError("Unsafe archive path")
    parts = PurePosixPath(name).parts
    if "//" in name or any(c in name for c in ("<", ">", "|", "?", "*", '"')):
        raise ValueError("Invalid Windows filename")
    if not parts or any(p in {".", ".."} or p.rstrip(" .") != p for p in parts):
        raise ValueError("Unsafe archive path")
    if any(
        p.lower() == ".local"
        or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", p)
        for p in parts
    ):
        raise ValueError("Private state/reserved names cannot occur in release files")
    if parts[0] not in COMPONENTS and name not in {"manifest.json", "release.json"}:
        raise ValueError("Unexpected release component")
    return parts


def verify_and_extract(archive, expected_sha, destination):
    if Path(archive).stat().st_size > MAX_ARCHIVE or sha256(archive) != expected_sha:
        raise ValueError("Release archive checksum/size mismatch")
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) > 60_000 or sum(i.file_size for i in entries) > MAX_EXPANDED:
            raise ValueError("Release expansion exceeds limits")
        seen = set()
        for entry in entries:
            safe_member(entry.filename.rstrip("/"))
            folded = entry.filename.rstrip("/").casefold()
            if folded in seen or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Duplicate/linked archive member")
            seen.add(folded)
        manifest = json.loads(bundle.read("manifest.json"))
        files = {
            i.filename
            for i in entries
            if not i.is_dir() and i.filename != "manifest.json"
        }
        if files != set(manifest):
            raise ValueError("Manifest must cover every release file exactly")
        for name, expected in manifest.items():
            digest = hashlib.sha256()
            target = destination.joinpath(*safe_member(name))
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(name) as source, target.open("xb") as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != expected:
                raise ValueError("Release file integrity failed: " + name)
        (destination / "manifest.json").write_bytes(bundle.read("manifest.json"))
    metadata = json.loads((destination / "release.json").read_text(encoding="utf-8"))
    if (
        metadata.get("product") != "bliss-mfa-windows"
        or metadata.get("provider_sha256") != PROVIDER_HASH
    ):
        raise ValueError("Wrong release product/provider")
    if not COMPONENTS.issubset({p.name for p in destination.iterdir()}):
        raise ValueError("Release lacks a required runtime component")
    if (
        sha256(destination / "installers/multiOTPCredentialProviderInstaller.msi")
        != PROVIDER_HASH
    ):
        raise ValueError("Provider payload integrity failed")
    return metadata


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def recover_interrupted(root, ops):
    """Recover a interrupted replacement from its private write-ahead journal."""
    root = Path(root).resolve()
    reject_links(root)
    for transaction in sorted(root.glob(".bliss-transaction-*")):
        journal_file = transaction / "journal.json"
        if not journal_file.exists():
            continue  # verification was interrupted before any installed change
        journal = json.loads(journal_file.read_text(encoding="utf-8"))
        if journal.get("root") != str(root) or journal.get("mode") not in {
            "repair",
            "update",
        }:
            continue
        if journal.get("phase") == "committed":
            shutil.rmtree(transaction)
            continue
        ops.stop(root)
        backup = transaction / "rollback"
        for name in sorted([*COMPONENTS, "manifest.json", "release.json"]):
            saved = backup / name
            if not saved.exists():
                continue
            current = root / name
            if current.is_dir():
                shutil.rmtree(current)
            elif current.exists():
                current.unlink()
            saved.rename(current)
        ops.start(root)
        ops.ready(root)
        shutil.rmtree(transaction)


def reject_links(root):
    for parent in [root, *root.parents]:
        if parent.exists() and (parent.is_symlink() or parent.is_junction()):
            raise ValueError("Installation may not traverse linked directories")
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            item = Path(base) / name
            if item.is_symlink() or item.is_junction():
                raise ValueError("Linked files are not supported in installed state")


@contextmanager
def installation_lock(root):
    with (root / ".installer.lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


class WindowsOps:
    def __init__(self, script):
        self.script = Path(script).resolve()

    def invoke(self, action, root, *arguments):
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.script),
                "-Action",
                action,
                "-Root",
                str(root),
                *arguments,
            ],
            check=True,
            timeout=600,
        )

    def protect(self, root):
        self.invoke("Protect", root)

    def stop(self, root):
        self.invoke("Stop", root)

    def start(self, root):
        self.invoke("Start", root)

    def ready(self, root):
        self.invoke("Ready", root)

    def install(self, root):
        self.invoke("Install", root)

    def repair(self, root):
        self.invoke("Repair", root)


def apply_archive(
    root, archive, expected_sha, mode, ops, update_config=None, descriptor=None
):
    root = Path(root).resolve()
    if root == root.parent or len(root.parts) < 2:
        raise ValueError("Refusing installation at filesystem root")
    reject_links(root)
    existed = root.exists()
    if mode == "install" and existed:
        raise ValueError("Installation directory already exists; use repair/update")
    if (
        mode != "install"
        and not (root / "bliss-mfa/.local/updater/installation.json").is_file()
    ):
        raise ValueError(
            "Managed installation identity missing; explicit prototype migration required"
        )
    root.mkdir(parents=True, exist_ok=True)
    ops.protect(root)
    with installation_lock(root):
        transaction = Path(tempfile.mkdtemp(prefix=".bliss-transaction-", dir=root))
        stage, backup = transaction / "stage", transaction / "rollback"
        stage.mkdir()
        backup.mkdir()
        moved = []
        added = []
        stopped = False
        state = root / "bliss-mfa/.local"
        saved_state = transaction / "state"
        success = False
        try:
            metadata = verify_and_extract(archive, expected_sha, stage)
            installed_path = state / "updater/installation.json"
            installed = (
                json.loads(installed_path.read_text(encoding="utf-8"))
                if installed_path.exists()
                else None
            )
            if descriptor and any(
                metadata[k] != descriptor[k]
                for k in ("version", "sequence", "channel", "provider_sha256")
            ):
                raise ValueError("Signed descriptor does not match the archive")
            if mode == "repair" and (
                metadata["sequence"] != installed["sequence"]
                or expected_sha != installed["sha256"]
            ):
                raise ValueError("Repair requires the exact installed release archive")
            if mode == "update" and metadata["sequence"] <= installed["sequence"]:
                raise ValueError("Downgrade/replay refused")
            cache = root / ".release-cache"
            cache.mkdir(exist_ok=True)
            cached = cache / (expected_sha + ".zip")
            if not cached.exists():
                shutil.copy2(archive, cached)
            if mode != "install":
                atomic_json(
                    transaction / "journal.json",
                    {"root": str(root), "mode": mode, "phase": "replacing"},
                )
                ops.stop(root)
                stopped = True
                if state.exists():
                    shutil.copytree(state, saved_state)
            for name in sorted([*COMPONENTS, "manifest.json", "release.json"]):
                current = root / name
                if current.exists():
                    current.rename(backup / name)
                    moved.append(name)
                (stage / name).rename(current)
                added.append(name)
            if saved_state.exists():
                shutil.copytree(saved_state, state)
            if mode == "install":
                atomic_json(
                    state / "updater/installation.json",
                    {
                        **metadata,
                        **(update_config or {}),
                        "sha256": expected_sha,
                        "status": "installing",
                    },
                )
                (state / "updater/update-public.pem").write_bytes(
                    (root / "bliss-mfa/deployment/update-public.pem").read_bytes()
                )
                ops.install(root)
            elif mode == "repair":
                ops.repair(root)
                ops.start(root)
            else:
                ops.start(root)
            ops.ready(root)
            # Write identity only after every startup check succeeds.
            settings = {
                **(installed or {}),
                **metadata,
                "sha256": expected_sha,
                "status": "ready",
                "updated_at": datetime.now(UTC).isoformat(),
            }
            if update_config:
                settings.update(update_config)
            atomic_json(state / "updater/installation.json", settings)
            if mode != "install":
                atomic_json(
                    transaction / "journal.json",
                    {"root": str(root), "mode": mode, "phase": "committed"},
                )
            success = True
            return settings
        except Exception:
            if mode == "install" and added:
                # Keep a failed first install repairable rather than removing
                # files still referenced by a partially installed service.
                ops.stop(root)
                success = True  # payload retained; private transaction can be discarded
                raise
            if added:
                ops.stop(root)
                for name in reversed(added):
                    target = root / name
                    if target.is_dir():
                        shutil.rmtree(target)
                    elif target.exists():
                        target.unlink()
                for name in moved:
                    (backup / name).rename(root / name)
                if stopped:
                    ops.start(root)
                    ops.ready(root)
                success = True  # rollback finished; discard this transaction
            raise
        finally:
            # Retain failed transaction evidence if rollback itself failed.
            if success or (
                not any(backup.iterdir())
                and not (transaction / "journal.json").exists()
            ):
                shutil.rmtree(transaction)


def check_backend(root, client=None):
    root = Path(root)
    state = root / "bliss-mfa/.local"
    installed = json.loads(
        (state / "updater/installation.json").read_text(encoding="utf-8")
    )
    public_key = state / "updater/update-public.pem"
    license_config = json.loads(
        (state / "engine/appliance.json").read_text(encoding="utf-8-sig")
    )
    license_state = Path(license_config["license_state_dir"])
    installation_id = json.loads(
        (license_state / "installation.json").read_text(encoding="utf-8")
    )["installation_id"]
    key = Ed25519PrivateKey.from_private_bytes(
        decode((license_state / "device.key").read_text().strip())
    )
    url = https_url(installed["updates_url"]).rstrip("/")
    with client or httpx.Client(
        timeout=30, trust_env=False, follow_redirects=False
    ) as transport:
        response = transport.post(
            url + "/v1/challenges", json={"installation_id": installation_id}
        )
        response.raise_for_status()
        message = {
            "action": "update-check",
            "installation_id": installation_id,
            "nonce": response.json()["nonce"],
            "channel": installed["channel"],
            "current_sequence": installed["sequence"],
        }
        request = {k: v for k, v in message.items() if k != "action"}
        request["signature"] = encode(key.sign(canonical(message)))
        response = transport.post(url + "/v1/updates/check", json=request)
        response.raise_for_status()
        envelope = response.json()["update"]
        if envelope is None:
            return None
        return verified_descriptor(
            envelope, public_key, installed["sequence"], installed["channel"]
        )


def download(descriptor, destination):
    with httpx.Client(timeout=120, trust_env=False, follow_redirects=False) as client:
        with client.stream("GET", https_url(descriptor["archive_url"])) as response:
            response.raise_for_status()
            size = 0
            with destination.open("xb") as out:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > descriptor["size"]:
                        raise ValueError("Download exceeds signed release size")
                    out.write(chunk)
    if size != descriptor["size"] or sha256(destination) != descriptor["sha256"]:
        raise ValueError("Downloaded release integrity failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "repair", "update", "check"])
    parser.add_argument("--root", type=Path, default=Path("C:/BlissMFA"))
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--updates-url")
    parser.add_argument("--update-public-key", type=Path)
    parser.add_argument("--automatic", action="store_true")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Installer requires Windows")
    ops = WindowsOps(Path(__file__).with_name("WindowsOps.ps1"))
    if args.root.exists():
        with installation_lock(args.root):
            recover_interrupted(args.root, ops)
    if args.action in {"check", "update"}:
        descriptor = check_backend(args.root)
        print(
            json.dumps(
                {"available": descriptor is not None, "release": descriptor}, indent=2
            )
        )
        if args.action == "check" or descriptor is None:
            return
        with tempfile.TemporaryDirectory(
            prefix=".bliss-download-", dir=args.root
        ) as folder:
            archive = Path(folder) / "release.zip"
            download(descriptor, archive)
            apply_archive(
                args.root,
                archive,
                descriptor["sha256"],
                "update",
                ops,
                descriptor=descriptor,
            )
    else:
        if args.action == "repair":
            identity = json.loads(
                (args.root / "bliss-mfa/.local/updater/installation.json").read_text(
                    encoding="utf-8"
                )
            )
            if not args.archive:
                args.sha256 = identity["sha256"]
                args.archive = args.root / ".release-cache" / (args.sha256 + ".zip")
        if not args.archive or not args.sha256:
            parser.error("Install/repair require --archive and --sha256")
        update_config = None
        if args.action == "install":
            if not args.updates_url or not args.update_public_key:
                parser.error(
                    "Installation requires updates URL and pinned update public key"
                )
            key = serialization.load_pem_public_key(args.update_public_key.read_bytes())
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError("Update public key must be Ed25519")
            update_config = {
                "updates_url": https_url(args.updates_url),
                "automatic_updates": args.automatic,
            }
        apply_archive(
            args.root, args.archive, args.sha256, args.action, ops, update_config
        )
        if args.action in {"install", "repair"}:
            key_path = args.root / "bliss-mfa/.local/updater/update-public.pem"
            if args.action == "install":
                key_path.write_bytes(args.update_public_key.read_bytes())
            ops.invoke(
                "Integration",
                args.root,
                "-ControlRoot",
                str(Path(__file__).resolve().parent.parent),
                *(
                    ["-AutomaticUpdates"]
                    if (
                        args.automatic
                        or (
                            args.action == "repair"
                            and identity.get("automatic_updates")
                        )
                    )
                    else []
                ),
            )


if __name__ == "__main__":
    main()
