import pytest

from appliance import main


@pytest.fixture(autouse=True)
def hermetic_windows_account_validation(monkeypatch):
    """Tests must never read the developer machine's real Windows accounts.

    Production defaults to "auto" (validate on a Windows host). Tests that exercise validation
    opt in explicitly and fake the account inventory.
    """
    monkeypatch.setattr(main.settings, "windows_account_validation", "off")
