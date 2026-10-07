"""Build a self-contained Windows installer from reviewed runtime inputs and source."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def archive_tree(root, destination, prefix=""):
    with zipfile.ZipFile(
        destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for file in sorted(root.rglob("*")):
            if file.is_file():
                archive.write(file, prefix + file.relative_to(root).as_posix())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("Built ZIP verification failed")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime-base", type=Path, required=True)
    p.add_argument("--engine-source", type=Path, required=True)
    p.add_argument("--update-public-key", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--sequence", type=int, required=True)
    p.add_argument("--channel", choices=["preview", "stable"], default="preview")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    portal = REPO / "apps/appliance-portal"
    if not (portal / ".next/standalone/server.js").is_file():
        raise ValueError("Build the appliance portal with output: standalone first")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not isinstance(
        serialization.load_pem_public_key(args.update_public_key.read_bytes()),
        Ed25519PublicKey,
    ):
        raise ValueError("Update key must be Ed25519")
    with tempfile.TemporaryDirectory(prefix="bliss-build-") as temporary:
        temporary = Path(temporary)
        payload, installer = temporary / "payload", temporary / "installer"
        payload.mkdir()
        installer.mkdir()
        runtime_hashes = {}
        for name in ["python", "node", "php-runtime", "installers"]:
            source = args.runtime_base / name
            if not source.is_dir():
                raise ValueError("Missing reviewed runtime: " + name)
            shutil.copytree(
                source,
                payload / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            for file in source.rglob("*"):
                if file.is_file() and file.suffix.lower() in {".exe", ".msi", ".dll"}:
                    runtime_hashes[file.relative_to(args.runtime_base).as_posix()] = (
                        digest(file)
                    )
        engine = payload / "multiotp-engine"
        engine.mkdir()
        # Two reviewed real-engine files; no pre-existing user/token databases.
        for name in ["multiotp.php", "multiotp.class.php"]:
            shutil.copy2(args.engine_source / name, engine / name)
            from php_framing import patch

            patch(engine / name)
        shutil.copytree(
            args.engine_source / "contrib",
            engine / "contrib",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        repo_payload = payload / "bliss-mfa"
        for relative in [
            "scripts",
            "deployment/engine-auth",
            "services/multiotp-adapter/adapter",
            "services/license-agent/license_agent",
            "apps/appliance-api/appliance",
        ]:
            shutil.copytree(
                REPO / relative,
                repo_payload / relative,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        (repo_payload / "deployment").mkdir(exist_ok=True)
        shutil.copy2(
            REPO / "deployment/license-public.pem",
            repo_payload / "deployment/license-public.pem",
        )
        shutil.copy2(
            args.update_public_key, repo_payload / "deployment/update-public.pem"
        )
        shutil.copytree(portal / ".next/standalone", payload / "portal")
        shutil.copytree(portal / ".next/static", payload / "portal/.next/static")
        if (portal / "public").exists():
            shutil.copytree(portal / "public", payload / "portal/public")
        for file in payload.rglob("*"):
            if file.is_file() and (
                ".local" in file.parts or file.suffix in {".key", ".pfx", ".p12"}
            ):
                raise ValueError("Private state/key in release: " + str(file))
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip()
        dirty = bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO).strip()
        )
        provider_hash = digest(
            payload / "installers/multiOTPCredentialProviderInstaller.msi"
        )
        metadata = {
            "product": "bliss-mfa-windows",
            "version": args.version,
            "sequence": args.sequence,
            "channel": args.channel,
            "provider_sha256": provider_hash,
            "source_revision": revision,
            "source_dirty": dirty,
            "built_at": datetime.now(UTC).isoformat(),
        }
        (payload / "release.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        manifest = {
            f.relative_to(payload).as_posix(): digest(f)
            for f in sorted(payload.rglob("*"))
            if f.is_file()
        }
        (payload / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        package = installer / "BlissMFA-Appliance.zip"
        archive_tree(payload, package)
        descriptor = {
            **metadata,
            "sha256": digest(package),
            "size": package.stat().st_size,
        }
        (args.output / "release-metadata.json").write_text(
            json.dumps(descriptor, indent=2), encoding="utf-8"
        )
        shutil.copytree(payload / "python", installer / "python")
        shutil.copytree(
            REPO / "windows_installer",
            installer / "windows_installer",
            ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"),
        )
        for name in ["Setup-BlissMFA.ps1", "Setup-BlissMFA.cmd"]:
            shutil.copy2(REPO / "windows_installer" / name, installer / name)
        shutil.copy2(args.update_public_key, installer / "update-public.pem")
        (installer / "installer.json").write_text(
            json.dumps(
                {
                    "version": args.version,
                    "archive_sha256": descriptor["sha256"],
                    "archive_size": descriptor["size"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        shutil.copy2(REPO / "windows_installer/README.md", installer / "START-HERE.md")
        destination = (
            args.output / f"Bliss-MFA-Windows-{args.version}-{args.channel}.zip"
        )
        archive_tree(installer, destination, "Bliss-MFA-Installer/")
        shutil.copy2(package, args.output / "BlissMFA-Appliance.zip")
        (args.output / "runtime-provenance.json").write_text(
            json.dumps(runtime_hashes, indent=2), encoding="utf-8"
        )
        (args.output / "SHA256SUMS.txt").write_text(
            digest(destination)
            + "  "
            + destination.name
            + "\n"
            + digest(args.output / "BlissMFA-Appliance.zip")
            + "  BlissMFA-Appliance.zip\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "installer": str(destination),
                    "bytes": destination.stat().st_size,
                    "sha256": digest(destination),
                    "release": descriptor,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
