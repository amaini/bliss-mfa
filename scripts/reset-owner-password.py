"""Reset the local portal owner's password. Windows administrator only; the new password is typed, never shown.

A Windows administrator on this computer already controls Bliss MFA, so administrator rights are the
recovery boundary. Other portal accounts are not changed. The reset is written to the audit log.

    & 'C:\\BlissMFA\\python\\python.exe' 'C:\\BlissMFA\\bliss-mfa\\scripts\\reset-owner-password.py'
"""
from __future__ import annotations

import ctypes
import getpass
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "appliance-api"))

MIN_LENGTH = 12


def reset_owner_password(database_file: Path, password: str) -> str:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from appliance.audit import write_audit
    from appliance.models import AdminRole, LocalAdmin
    from appliance.security import hash_password

    if len(password) < MIN_LENGTH:
        raise ValueError(f"Use at least {MIN_LENGTH} characters")
    engine = create_engine(f"sqlite+pysqlite:///{Path(database_file).as_posix()}")
    try:
        with Session(engine) as db:
            owner = db.scalar(select(LocalAdmin).where(LocalAdmin.role == AdminRole.owner).order_by(LocalAdmin.email))
            if not owner:
                raise RuntimeError("No portal owner exists; complete setup from the setup page instead")
            owner.password_hash = hash_password(password)
            owner.disabled = False
            write_audit(db, actor_id=None, action="admin.owner_password_reset", subject_type="local_admin",
                        subject_id=owner.id, reason="Reset by a Windows administrator on this computer")
            db.commit()
            return owner.email
    finally:
        engine.dispose()


def main() -> None:
    if os.name != "nt" or not ctypes.windll.shell32.IsUserAnAdmin():
        raise SystemExit("Run this from an elevated (Run as administrator) PowerShell.")
    root = REPO.parent
    appliance = json.loads((REPO / ".local/engine/appliance.json").read_text(encoding="utf-8-sig"))
    password = getpass.getpass("New portal owner password (12+ characters): ")
    if getpass.getpass("Repeat it: ") != password:
        raise SystemExit("Passwords differ; nothing was changed.")
    email = reset_owner_password(Path(appliance["database_file"]), password)
    print(f"Password reset for portal owner {email}. Sign in at https://localhost:19443 ({root}).")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        raise SystemExit(f"Reset failed: {error}") from None
