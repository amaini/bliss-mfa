import pytest

from adapter.runner import AdapterInputError, MultiOtpCliRunner, validate_otp, validate_username


def test_username_validation() -> None:
    assert validate_username("tenant:alice") == "tenant:alice"
    with pytest.raises(AdapterInputError):
        validate_username("-debug")


def test_otp_validation() -> None:
    assert validate_otp("123456") == "123456"
    with pytest.raises(AdapterInputError):
        validate_otp("12ab56")


def test_runner_never_uses_shell(monkeypatch) -> None:
    captured = {}

    class Result:
        returncode = 0
        stdout = "alice\n"
        stderr = ""

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr("adapter.runner.subprocess.run", fake_run)

    runner = MultiOtpCliRunner("/opt/multiotp.php")
    runner.users_list()

    assert captured["args"] == ["/opt/multiotp.php", "-userslist"]
    assert captured["kwargs"]["shell"] is False


def test_php_launch_preserves_spaces_without_shell(tmp_path, monkeypatch):
    from adapter.config import get_settings
    monkeypatch.setenv("MULTIOTP_PHP_EXECUTABLE", "C:/Program Files/php/php.exe")
    monkeypatch.setenv("MULTIOTP_PHP_EXTENSION_DIR", "C:/Program Files/php/ext")
    monkeypatch.setenv("MULTIOTP_BASE_DIR", str(tmp_path / "engine state"))
    get_settings.cache_clear()
    captured = {}

    def fake_run(args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return type("Result", (), {"returncode": 11, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("adapter.runner.subprocess.run", fake_run)
    try:
        result = MultiOtpCliRunner("C:/Program Files/multiotp/multiotp.php").create_totp_user("alice")
        assert result.returncode == 11
        assert captured["args"][0] == "C:/Program Files/php/php.exe"
        assert captured["args"][-2:] == ["-fastcreatenopin", "alice"]
        assert captured["args"][-3].endswith("engine state/")
        assert captured["kwargs"]["shell"] is False
    finally:
        get_settings.cache_clear()
