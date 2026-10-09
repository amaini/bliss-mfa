import pytest

from appliance.rdp_protection import OFF_VALUES, ON_VALUES, ProviderRegistry, ProviderWriteError


class FakeBackend:
    def __init__(self, values=None, corrupt=None):
        self.values = dict(values if values is not None else {
            "cpus_logon": "3d", "cpus_unlock": "3d", "cpus_credui": "3d",
            "excluded_account": r"UX8402ZE\Abhishek"})
        self.flushes = 0
        self.corrupt = corrupt  # name whose write silently fails once
        self.written = []

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value, kind):
        self.written.append(name)
        if name == self.corrupt:
            self.corrupt = None
            return
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)

    def flush(self):
        self.flushes += 1


def test_apply_on_writes_exact_values_and_flushes():
    backend = FakeBackend()
    ProviderRegistry(backend).apply(True)
    for name, (value, _) in ON_VALUES.items():
        assert backend.values[name] == value
    assert backend.flushes >= 1
    assert "two_step_send_password" not in backend.written
    assert "excluded_account" not in backend.written


def test_apply_off_sets_cpus_3d():
    backend = FakeBackend()
    registry = ProviderRegistry(backend)
    registry.apply(True)
    registry.apply(False)
    assert {n: backend.values[n] for n in OFF_VALUES} == {n: v for n, (v, _) in OFF_VALUES.items()}
    assert registry.is_on() is False


def test_readback_mismatch_restores_previous_values():
    backend = FakeBackend(corrupt="cpus_unlock")
    before = dict(backend.values)
    with pytest.raises(ProviderWriteError):
        ProviderRegistry(backend).apply(True)
    for name in ("cpus_logon", "cpus_unlock", "cpus_credui"):
        assert backend.values.get(name) == before.get(name)
    assert backend.values.get("two_step_hide_otp") is None


def test_is_on_requires_remote_only_values():
    assert ProviderRegistry(FakeBackend()).is_on() is False
    backend = FakeBackend()
    ProviderRegistry(backend).apply(True)
    backend.values.update(cpus_logon="0e")  # local+remote is not a state Bliss sets
    assert ProviderRegistry(backend).is_on() is False


def test_recovery_account_name():
    assert ProviderRegistry(FakeBackend()).recovery_account() == "Abhishek"
    assert ProviderRegistry(FakeBackend({})).recovery_account() is None
