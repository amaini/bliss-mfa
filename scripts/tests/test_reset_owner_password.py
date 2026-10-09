import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("argon2")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps" / "appliance-api"))
spec = importlib.util.spec_from_file_location("reset_owner", REPO / "scripts" / "reset-owner-password.py")
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)

from appliance.db import Base
from appliance.models import AdminRole, AuditEvent, LocalAdmin
from appliance.security import hash_password, verify_password
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "appliance.db"
    engine = create_engine(f"sqlite+pysqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LocalAdmin(email="owner@example.com", password_hash=hash_password("old-password-123"), role=AdminRole.owner))
        db.add(LocalAdmin(email="ops@example.com", password_hash=hash_password("ops-password-123"), role=AdminRole.operator))
        db.commit()
    engine.dispose()
    return path


def admins(path):
    engine = create_engine(f"sqlite+pysqlite:///{path.as_posix()}")
    with Session(engine) as db:
        rows = {a.email: a for a in db.scalars(select(LocalAdmin))}
        events = [e.action for e in db.scalars(select(AuditEvent))]
    engine.dispose()
    return rows, events


def test_resets_only_the_owner_and_audits(database):
    email = reset.reset_owner_password(database, "new-owner-password-1")
    rows, events = admins(database)
    assert email == "owner@example.com"
    assert verify_password(rows["owner@example.com"].password_hash, "new-owner-password-1")
    assert not verify_password(rows["owner@example.com"].password_hash, "old-password-123")
    assert verify_password(rows["ops@example.com"].password_hash, "ops-password-123")
    assert events == ["admin.owner_password_reset"]


def test_rejects_short_password(database):
    with pytest.raises(ValueError, match="12"):
        reset.reset_owner_password(database, "short")
    rows, events = admins(database)
    assert verify_password(rows["owner@example.com"].password_hash, "old-password-123") and events == []


def test_reenables_a_disabled_owner(database):
    engine = create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    with Session(engine) as db:
        db.scalar(select(LocalAdmin).where(LocalAdmin.role == AdminRole.owner)).disabled = True
        db.commit()
    engine.dispose()
    reset.reset_owner_password(database, "new-owner-password-1")
    rows, _ = admins(database)
    assert rows["owner@example.com"].disabled is False
