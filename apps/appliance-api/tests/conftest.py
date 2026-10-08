import pytest

from appliance import main


@pytest.fixture(autouse=True)
def hermetic_windows_account_validation(monkeypatch):
    """Tests must never read the developer machine's real Windows accounts.

    Production defaults to "auto" (validate on a Windows host). Tests that exercise validation
    opt in explicitly and fake the account inventory.
    """
    monkeypatch.setattr(main.settings, "windows_account_validation", "off")


@pytest.fixture(autouse=True)
def hermetic_provider_registry(monkeypatch):
    """Tests must never read or write the developer machine's real sign-in provider settings."""
    from appliance.rdp_protection import ProviderRegistry
    from tests.test_rdp_protection_registry import FakeBackend
    monkeypatch.setattr(main, "provider_registry", lambda: ProviderRegistry(FakeBackend({})))
