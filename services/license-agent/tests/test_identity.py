import pytest

from license_agent.state import IdentityLostError, LicenseState


def test_new_installation_creates_identity_once(tmp_path):
    state = LicenseState(str(tmp_path))
    first = state.installation_id()
    key = state.public_key_b64()
    again = LicenseState(str(tmp_path))
    assert again.installation_id() == first
    assert again.public_key_b64() == key


@pytest.mark.parametrize("evidence", ["lease.token", "trusted-time.json", "released.json"])
@pytest.mark.parametrize("missing", ["installation.json", "device.key"])
def test_activated_installation_never_mints_replacement_identity(tmp_path, evidence, missing):
    state = LicenseState(str(tmp_path))
    state.installation_id()
    state.public_key_b64()
    (tmp_path / evidence).write_text("x")
    (tmp_path / missing).unlink()

    if missing == "installation.json":
        with pytest.raises(IdentityLostError):
            LicenseState(str(tmp_path)).installation_id()
    with pytest.raises(IdentityLostError):
        LicenseState(str(tmp_path)).public_key_b64()
    assert not (tmp_path / missing).exists()


def test_orphan_device_key_without_installation_id_is_lost(tmp_path):
    state = LicenseState(str(tmp_path))
    state.installation_id()
    state.public_key_b64()
    (tmp_path / "installation.json").unlink()
    with pytest.raises(IdentityLostError):
        LicenseState(str(tmp_path)).installation_id()


def test_lost_identity_reports_status_without_crashing(tmp_path):
    state = LicenseState(str(tmp_path))
    state.installation_id()
    (tmp_path / "lease.token").write_text("x")
    (tmp_path / "installation.json").unlink()
    status = LicenseState(str(tmp_path)).effective_status()
    assert status["state"] == "identity_lost"
    assert status["max_rdp_users"] == 0


def test_lost_identity_blocks_new_seats_only(tmp_path):
    state = LicenseState(str(tmp_path))
    state.installation_id()
    (tmp_path / "lease.token").write_text("x")
    (tmp_path / "installation.json").unlink()
    result = LicenseState(str(tmp_path)).reserve_seat("alice")
    assert result["allowed"] is False
    assert "identity_lost" in result["reason"]
