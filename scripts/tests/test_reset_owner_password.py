import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def m():
    """Load the reset tool and the appliance models (skipped where the API's packages are not installed)."""
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("argon2")
    sys.path.insert(0, str(REPO / "apps" / "appliance-api"))
    spec = importlib.util.spec_from_file_location("reset_owner", REPO / "scripts" / "reset-owner-password.py")
    reset = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reset)
    import sqlalchemy
    import sqlalchemy.orm
    from appliance import db, models, security
    return type("Modules", (), {"reset": reset, "sa": sqlalchemy, "orm": sqlalchemy.orm, "db": db,
                                "models": models, "security": security})


@pytest.fixture
def database(tmp_path, m):
    path = tmp_path / "appliance.db"
    engine = m.sa.create_engine(f"sqlite+pysqlite:///{path.as_posix()}")
    m.db.Base.metadata.create_all(engine)
    with m.orm.Session(engine) as session:
        session.add(m.models.LocalAdmin(email="owner@example.com", role=m.models.AdminRole.owner,
                                        password_hash=m.security.hash_password("old-password-123")))
        session.add(m.models.LocalAdmin(email="ops@example.com", role=m.models.AdminRole.operator,
                                        password_hash=m.security.hash_password("ops-password-123")))
        session.commit()
    engine.dispose()
    return path


def admins(m, path):
    engine = m.sa.create_engine(f"sqlite+pysqlite:///{path.as_posix()}")
    with m.orm.Session(engine) as session:
        rows = {a.email: a for a in session.scalars(m.sa.select(m.models.LocalAdmin))}
        events = [e.action for e in session.scalars(m.sa.select(m.models.AuditEvent))]
    engine.dispose()
    return rows, events


def test_resets_only_the_owner_and_audits(m, database):
    email = m.reset.reset_owner_password(database, "new-owner-password-1")
    rows, events = admins(m, database)
    assert email == "owner@example.com"
    assert m.security.verify_password(rows["owner@example.com"].password_hash, "new-owner-password-1")
    assert not m.security.verify_password(rows["owner@example.com"].password_hash, "old-password-123")
    assert m.security.verify_password(rows["ops@example.com"].password_hash, "ops-password-123")
    assert events == ["admin.owner_password_reset"]


def test_rejects_short_password(m, database):
    with pytest.raises(ValueError, match="12"):
        m.reset.reset_owner_password(database, "short")
    rows, events = admins(m, database)
    assert m.security.verify_password(rows["owner@example.com"].password_hash, "old-password-123") and events == []


def test_reenables_a_disabled_owner(m, database):
    engine = m.sa.create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    with m.orm.Session(engine) as session:
        session.scalar(m.sa.select(m.models.LocalAdmin).where(m.models.LocalAdmin.role == m.models.AdminRole.owner)).disabled = True
        session.commit()
    engine.dispose()
    m.reset.reset_owner_password(database, "new-owner-password-1")
    rows, _ = admins(m, database)
    assert rows["owner@example.com"].disabled is False
