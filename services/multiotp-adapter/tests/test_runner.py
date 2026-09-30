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
