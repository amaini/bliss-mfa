import json
import subprocess

import pytest

from appliance import native_verify as nv


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"auth_port": 18443, "native_shared_secret": "s3cret"}))
    monkeypatch.setattr(nv.settings, "engine_config_file", str(path))
    monkeypatch.setattr(nv.settings, "provider_validation_dir", str(tmp_path / "pv"))
    return tmp_path


def test_success_exit_zero_and_arguments(config):
    seen = {}

    def run(args, **kw):
        seen["args"] = args
        return subprocess.CompletedProcess(args, 0, "", "")
    assert nv.native_verify("Ekta", "123456", run=run, client="C:/m/multiotp.exe") is True
    a = seen["args"]
    assert a[0] == "C:/m/multiotp.exe" and a[1] == "-cp" and a[-2:] == ["Ekta", "123456"]
    assert "-server-url=https://127.0.0.1:18443/auth" in a and "-server-secret=s3cret" in a
    assert not any(x.endswith("\\") for x in a)  # trailing backslash corrupts multiotp.exe quoting


def test_failure_codes(config):
    for code in (21, 99):
        assert nv.native_verify("Ekta", "123456", client="c",
                                run=lambda a, code=code, **k: subprocess.CompletedProcess(a, code, "", "")) is False


def test_rejects_malformed_code_without_calling(config):
    called = []
    with pytest.raises(ValueError):
        nv.native_verify("Ekta", "12ab56", client="c", run=lambda *a, **k: called.append(1))
    assert not called


def test_unavailable_without_config(monkeypatch):
    monkeypatch.setattr(nv.settings, "engine_config_file", None)
    with pytest.raises(nv.NativeVerifyUnavailable):
        nv.native_verify("Ekta", "123456", client="c")
