from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from appliance.db import Base
from appliance.migrate import VERSION_TABLE, migrate
from appliance.models import (
    AdminRole,
    AuditEvent,
    BootstrapSeal,
    LocalAdmin,
    MfaUser,
    UserStatus,
    event_digest,
    utcnow,
)


@pytest.fixture
def database(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "appliance.db"))
    yield engine
    engine.dispose()


def test_clean_and_concurrent_startup(database):
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: migrate(database), range(2)))
    migrate(database)
    with database.connect() as connection:
        assert connection.execute(text(
            f"SELECT id, version FROM {VERSION_TABLE}"
        )).all() == [(1, 1)]
    assert set(inspect(database).get_table_names()) == set(Base.metadata.tables) | {VERSION_TABLE}


def test_legacy_adoption_preserves_owner_seal_users_and_audit(database):
    Base.metadata.create_all(database)
    created = utcnow()
    digest_args = {"actor_id": "owner", "action": "mfa.user.created",
                   "subject_type": "mfa_user", "subject_id": "user", "reason": None,
                   "success": True, "previous_hash": None, "created_at": created}
    digest = event_digest(**digest_args)
    with Session(database) as db:
        db.add(LocalAdmin(id="owner", email="owner@example.com", password_hash="original-hash",
                          role=AdminRole.owner))
        db.add(BootstrapSeal(id=1))
        db.add(MfaUser(id="user", username="WindowsUser", engine_username="windowsuser",
                       status=UserStatus.active))
        db.add(AuditEvent(id="event", event_hash=digest, **digest_args))
        db.commit()
    with database.connect() as connection:
        before = {name: connection.execute(select(table)).all()
                  for name, table in Base.metadata.tables.items()}
    migrate(database)
    migrate(database)
    with database.connect() as connection:
        after = {name: connection.execute(select(table)).all()
                 for name, table in Base.metadata.tables.items()}
    assert after == before
    with Session(database) as db:
        event = db.get(AuditEvent, "event")
        assert event.event_hash == event_digest(**{
            key: getattr(event, key) for key in digest_args
        })


@pytest.mark.parametrize("damage", ["table", "column", "unique", "type", "foreign"])
def test_unknown_legacy_schema_is_not_repaired(database, damage):
    Base.metadata.create_all(database)
    with database.begin() as connection:
        if damage == "table":
            connection.execute(text("DROP TABLE bootstrap_seal"))
        elif damage == "column":
            connection.execute(text("ALTER TABLE mfa_users ADD COLUMN unknown TEXT"))
        elif damage == "unique":
            connection.execute(text("DROP INDEX ix_local_admins_email"))
        elif damage == "type":
            connection.execute(text("DROP TABLE bootstrap_seal"))
            connection.execute(text(
                "CREATE TABLE bootstrap_seal (id TEXT NOT NULL PRIMARY KEY, "
                "created_at DATETIME NOT NULL)"
            ))
        else:
            connection.execute(text("CREATE TABLE unrelated (value TEXT)"))
            connection.execute(text("INSERT INTO unrelated VALUES ('preserve-me')"))
    with pytest.raises(RuntimeError, match="schema|uniqueness"):
        migrate(database)
    assert VERSION_TABLE not in inspect(database).get_table_names()
    if damage == "foreign":
        with database.connect() as connection:
            assert connection.execute(text("SELECT value FROM unrelated")).scalar_one() == "preserve-me"


@pytest.mark.parametrize("damage", ["newer", "empty", "missing"])
def test_versioned_schema_refuses_downgrade_or_damage(database, damage):
    migrate(database)
    with database.begin() as connection:
        if damage == "newer":
            connection.execute(text(f"UPDATE {VERSION_TABLE} SET version=2"))
        elif damage == "empty":
            connection.execute(text(f"DELETE FROM {VERSION_TABLE}"))
        else:
            connection.execute(text("DROP TABLE audit_events"))
    with pytest.raises(RuntimeError):
        migrate(database)
    if damage == "missing":
        assert "audit_events" not in inspect(database).get_table_names()
