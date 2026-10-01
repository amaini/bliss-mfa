import pytest
from sqlalchemy import create_engine, inspect, text

from license_server.migrate import migrate


def test_clean_schema_and_repeat_start():
    engine = create_engine('sqlite://')
    migrate(engine)
    assert {'customers', 'licenses', 'bliss_schema_version'} <= set(inspect(engine).get_table_names())
    migrate(engine)


def test_unversioned_data_is_preserved():
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE valuable (data TEXT)'))
        db.execute(text("INSERT INTO valuable VALUES ('preserved')"))
    with pytest.raises(RuntimeError):
        migrate(engine)
    with engine.connect() as db:
        assert db.execute(text('SELECT data FROM valuable')).scalar_one() == 'preserved'


def test_version_one_upgrade_preserves_existing_customer(database_engine):
    from license_server.customer_models import CustomerTrial
    migrate(database_engine)
    with database_engine.begin() as db:
        CustomerTrial.__table__.drop(bind=db)
        db.execute(text('UPDATE bliss_schema_version SET version=1'))
        db.execute(text("INSERT INTO customers (id,email,company_name,password_hash,created_at) VALUES ('existing','existing@example.com','Existing','unchanged','2026-01-01')"))
    migrate(database_engine)
    migrate(database_engine)
    with database_engine.connect() as db:
        assert db.execute(text('SELECT version FROM bliss_schema_version')).scalar_one() == 2
        assert db.execute(text('SELECT password_hash FROM customers')).scalar_one() == 'unchanged'
