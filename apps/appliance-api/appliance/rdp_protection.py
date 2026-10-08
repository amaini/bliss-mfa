"""Fixed-value control of the multiOTP Credential Provider for RDP-only protection.

Only the values below are ever written. Every write is flushed to disk (RegFlushKey) and read back,
so neither a partial write nor a power cut can silently leave a different sign-in policy.
"""
from __future__ import annotations

PROVIDER_KEY = r"CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}"
ON_VALUES = {
    "cpus_logon": ("1e", "sz"), "cpus_unlock": ("1e", "sz"), "cpus_credui": ("3d", "sz"),
    "two_step_hide_otp": (1, "dword"), "multiOTPWithout2FA": (1, "dword"),
}
OFF_VALUES = {"cpus_logon": ("3d", "sz"), "cpus_unlock": ("3d", "sz"), "cpus_credui": ("3d", "sz")}
MANAGED = tuple(ON_VALUES)


class ProviderWriteError(RuntimeError):
    pass


class WinregBackend:
    def __init__(self) -> None:
        import winreg
        self.winreg = winreg
        self.key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, PROVIDER_KEY, 0,
                                  winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY)

    def get(self, name):
        try:
            return self.winreg.QueryValueEx(self.key, name)[0]
        except FileNotFoundError:
            return None

    def set(self, name, value, kind):
        kinds = {"sz": self.winreg.REG_SZ, "dword": self.winreg.REG_DWORD}
        self.winreg.SetValueEx(self.key, name, 0, kinds[kind], value)

    def delete(self, name):
        try:
            self.winreg.DeleteValue(self.key, name)
        except FileNotFoundError:
            pass

    def flush(self):
        self.winreg.FlushKey(self.key)


class ProviderRegistry:
    def __init__(self, backend=None) -> None:
        self.backend = backend or WinregBackend()

    def read(self) -> dict:
        return {name: self.backend.get(name) for name in (*MANAGED, "excluded_account")}

    def is_on(self) -> bool:
        values = self.read()
        return all(values[name] == value for name, (value, _) in ON_VALUES.items())

    def recovery_account(self) -> str | None:
        excluded = self.backend.get("excluded_account")
        return str(excluded).split("\\")[-1] if excluded else None

    def apply(self, on: bool) -> None:
        target = ON_VALUES if on else OFF_VALUES
        previous = {name: self.backend.get(name) for name in target}
        kinds = {name: kind for name, (_, kind) in target.items()}
        try:
            for name, (value, kind) in target.items():
                self.backend.set(name, value, kind)
            self.backend.flush()
            if any(self.backend.get(name) != value for name, (value, _) in target.items()):
                raise ProviderWriteError("Sign-in settings did not save as expected")
        except Exception:
            for name, value in previous.items():
                if value is None:
                    self.backend.delete(name)
                else:
                    self.backend.set(name, value, kinds[name])
            self.backend.flush()
            raise
