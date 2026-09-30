from app.multiotp.mock import MockMultiOtpAdapter


def test_mock_user_lifecycle() -> None:
    adapter = MockMultiOtpAdapter()
    adapter.create_totp_user("alice")

    assert adapter.get_user("alice") is not None
    material = adapter.begin_enrollment("alice")
    assert material.provisioning_uri.startswith("otpauth://")
    assert adapter.verify_otp("alice", "000000")

    adapter.disable_user("alice")
    assert adapter.get_user("alice").active is False

    adapter.enable_user("alice")
    assert adapter.get_user("alice").active is True

    adapter.delete_user("alice")
    assert adapter.get_user("alice") is None
