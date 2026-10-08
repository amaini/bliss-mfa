"""Development-only demo backend for the Windows Accounts page. NEVER use on a real appliance.

Runs the real appliance API with fakes: a made-up local account inventory (no Windows account is
read), an in-memory multiOTP engine (no MFA record is created in multiOTP) and a license agent with
a small seat limit. Data lives in a throwaway SQLite file.

    apps/appliance-api/.venv/Scripts/python tools/dev_windows_accounts_demo.py --db <path> --port 8765
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "appliance-api"))

FAKE_ACCOUNTS = [
    {"username": "Administrator", "display_name": None, "enabled": False},
    {"username": "demo.alice", "display_name": "Alice Demo", "enabled": True},
    {"username": "demo.bob", "display_name": "Bob Demo", "enabled": True},
    {"username": "demo.carol", "display_name": "Carol Demo", "enabled": True},
    {"username": "demo.disabled", "display_name": "Old Account", "enabled": False},
    {"username": "Guest", "display_name": None, "enabled": False},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--seats", type=int, default=3)
    args = parser.parse_args()
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{Path(args.db).as_posix()}"
    os.environ["APP_ENV"] = "test"  # no heartbeat scheduler
    os.environ.setdefault("SETUP_TOKEN", "demo-setup-token")
    os.environ["WINDOWS_ACCOUNT_VALIDATION"] = "required"

    import uvicorn

    from appliance import main as appliance

    class FakeEngine:
        def __init__(self): self.kind = {}
        def create_user(self, username): self.kind[username.lower()] = "t"
        def provisioning_uri(self, username): return f"otpauth://totp/BlissDemo:{username}?secret=JBSWY3DPEHPK3PXP&issuer=BlissDemo"
        def verify(self, username, otp): return otp == "000000"
        def delete_user(self, username): self.kind.pop(username.lower(), None); return True
        def ensure_without2fa(self, username):
            if self.kind.get(username.lower()) == "t":
                return False
            self.kind[username.lower()] = "w"
            return True

    class DemoProviderBackend:  # in-memory sign-in provider settings; nothing real is changed
        values = {"cpus_logon": "3d", "cpus_unlock": "3d", "cpus_credui": "3d", "excluded_account": r"DEMO-PC\Administrator"}
        def get(self, name): return self.values.get(name)
        def set(self, name, value, kind): self.values[name] = value
        def delete(self, name): self.values.pop(name, None)
        def flush(self): pass

    from appliance.rdp_protection import ProviderRegistry
    appliance.provider_registry = lambda: ProviderRegistry(DemoProviderBackend())
    appliance.native_verify = lambda username, otp: otp == "000000"

    reserved: set[str] = set()

    class FakeAgent:
        def status(self): return {"state": "active", "seat_limit": args.seats, "seats_used": len(reserved)}
        def reserve_seat(self, username):
            if username in reserved:
                return {"allowed": True, "already_reserved": True}
            if len(reserved) >= args.seats:
                return {"allowed": False, "reason": f"Seat limit reached: {args.seats} of {args.seats} protected users in use"}
            reserved.add(username)
            return {"allowed": True}
        def release_seat(self, username):
            reserved.discard(username)
            return len(reserved)
        def heartbeat(self, *a, **k): return {}

    engine, agent = FakeEngine(), FakeAgent()
    appliance.multiotp = lambda: engine
    appliance.license_agent = lambda: agent
    appliance.read_local_windows_accounts = lambda: [dict(a) for a in FAKE_ACCOUNTS]
    uvicorn.run(appliance.app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
