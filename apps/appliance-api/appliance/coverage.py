"""Keep every enabled local account known to multiOTP while RDP protection is on.

Enrolled accounts keep their TOTP record. Every other enabled account gets a without2FA record
(password-only RDP, no license seat); accounts unknown to multiOTP would be refused over RDP.
"""
from __future__ import annotations

from .models import UserStatus

PROTECTED = {UserStatus.active, UserStatus.pending, UserStatus.locked, UserStatus.disabled}


def reconcile(accounts, mfa_users, engine, recovery):
    records = {u.username.lower(): u for u in mfa_users}
    result = {"password_only": [], "protected": [], "errors": []}
    for account in accounts:
        name = account["username"]
        if not account["enabled"] or (recovery and name.lower() == recovery.lower()):
            continue
        record = records.get(name.lower())
        if record and record.status in PROTECTED:
            result["protected"].append(name)
            continue
        try:
            if not engine.ensure_without2fa(name):
                if not (record and record.status == UserStatus.revoked):
                    raise RuntimeError("TOTP record without a Bliss enrollment")
                engine.delete_user(name)
                if not engine.ensure_without2fa(name):
                    raise RuntimeError("Could not create password-only record")
            result["password_only"].append(name)
        except Exception:  # noqa: BLE001 - one account must not block the others
            result["errors"].append(name)
    return result
