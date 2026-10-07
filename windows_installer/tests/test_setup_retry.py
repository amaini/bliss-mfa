"""Exercise bootstrap retry logic in a private fixture, with all platform actions stubbed."""

import json
import os
from pathlib import Path
import subprocess

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows bootstrap")
SOURCE = Path(__file__).resolve().parents[1] / "Setup-BlissMFA.ps1"


@pytest.fixture
def setup(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    for name in ("python/python.exe", "windows_installer/manager.py", "update-public.pem"):
        file = bundle / name
        file.parent.mkdir(exist_ok=True)
        file.write_text("fixture")
    (bundle / "installer.json").write_text(json.dumps({"version": "0.2.0", "archive_sha256": "fixture"}))
    script = SOURCE.read_text()
    start = script.index("$principal=New-Object")
    end = script.index("try {", start)
    script = script[:start] + script[end:]
    script = script.replace("$env:ProgramFiles", "$env:BLISS_TEST_PROGRAMS")
    script = script.replace(
        "& icacls.exe $parent /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null",
        "$global:LASTEXITCODE=0",
    )
    script = script.replace(
        "& $python @arguments",
        "$arguments | ConvertTo-Json | Set-Content -LiteralPath $env:BLISS_TEST_ARGS; $global:LASTEXITCODE=0",
    )
    (bundle / SOURCE.name).write_text(script)
    env = {**os.environ, "BLISS_TEST_PROGRAMS": str(tmp_path / "programs"), "BLISS_TEST_ARGS": str(tmp_path / "args.json")}
    # A PowerShell 7 parent must not override Windows PowerShell's module paths.
    env["PSModulePath"] = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/Modules")

    def run():
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(bundle / SOURCE.name), "-Root", str(tmp_path / "appliance")],
            env=env, capture_output=True, text=True, timeout=30,
        )

    return bundle, run, tmp_path


def test_existing_legacy_updater_and_repeat_setup_are_retryable(setup):
    _, run, root = setup
    legacy = root / "programs/Bliss MFA Updater/0.2.0"
    legacy.mkdir(parents=True)
    (legacy / "partial.txt").write_text("preserve")
    assert run().returncode == 0
    assert run().returncode == 0
    assert json.loads((root / "args.json").read_text(encoding="utf-8-sig"))[1] == "install"
    assert (legacy / "partial.txt").read_text() == "preserve"


def test_managed_retry_selects_repair_without_changing_state(setup):
    _, run, root = setup
    receipt = root / "appliance/bliss-mfa/.local/updater/installation.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"status":"installing"}')
    assert run().returncode == 0
    assert json.loads((root / "args.json").read_text(encoding="utf-8-sig"))[1] == "repair"
    assert receipt.read_text() == '{"status":"installing"}'


def test_interrupted_controller_copy_does_not_block_retry(setup):
    bundle, run, root = setup
    missing = bundle / "update-public.pem"
    missing.unlink()
    assert run().returncode == 1
    missing.write_text("fixture")
    assert run().returncode == 0


def test_unmanaged_installation_is_preserved_and_rejected(setup):
    _, run, root = setup
    appliance = root / "appliance"
    appliance.mkdir()
    state = appliance / "legacy-state.txt"
    state.write_text("preserve")
    result = run()
    assert result.returncode == 1
    assert "without a managed receipt" in result.stdout
    assert state.read_text() == "preserve"


def test_existing_controller_corruption_is_rejected(setup):
    _, run, root = setup
    assert run().returncode == 0
    controller = next((root / "programs/Bliss MFA Updater").glob("0.2.0-*"))
    (controller / "windows_installer/manager.py").write_text("corrupted")
    result = run()
    assert result.returncode == 1
    assert "verification failed" in result.stdout
