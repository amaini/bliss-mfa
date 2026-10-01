from datetime import timedelta

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from license_server.config import Settings
from license_server.customer_auth import hash_password, password_matches
from license_server.customer_models import (
    Customer,
    CustomerLicense,
    CustomerToken,
    PaymentEvent,
    Purchase,
)
from license_server.db import Base, database_url
from license_server.import_sqlite import transfer
from license_server.migrate import migrate, require_import
from license_server.models import (
    ActivationEvent,
    Challenge,
    License,
    LicenseStatus,
    LicenseType,
    utcnow,
)


@pytest.fixture
def source(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'source.db'))
    migrate(engine)
    with Session(engine) as db:
        db.add(Customer(id='cus_source', email='owner@example.com', company_name='Office',
                        password_hash=hash_password('correct-horse-test-only'), verified_at=utcnow()))
        db.add(License(id='lic_source', customer_name='Office', license_type=LicenseType.online,
                       status=LicenseStatus.active, max_rdp_users=2,
                       stripe_subscription_id='sub_source', activation_code_hash='activationhash',
                       installation_id='installation1'))
        db.commit()
        db.add(CustomerToken(token_hash='tokenhash', customer_id='cus_source', purpose='session',
                             expires_at=utcnow()+timedelta(hours=1)))
        db.add(Purchase(id='buy_source', customer_id='cus_source', seats=2, price_id='price_source',
                        session_id='cs_source', status='fulfilled'))
        db.add(CustomerLicense(customer_id='cus_source', license_id='lic_source', subscription_id='sub_source'))
        db.add(PaymentEvent(id='evt_source', event_type='invoice.paid'))
        db.add(ActivationEvent(id='audit_source', license_id='lic_source', event_type='activated'))
        db.add(Challenge(nonce_hash='noncehash', installation_id='installation1', expires_at=utcnow()))
        db.commit()
    yield engine
    engine.dispose()


def test_preserves_every_table_password_and_license(source, database_engine):
    result = transfer(source, database_engine, confirm_maintenance=True)
    assert set(result) == set(Base.metadata.tables)
    assert all(count == 1 for name, count in result.items() if name != 'customer_trials')
    assert result['customer_trials'] == 0
    with Session(database_engine) as db:
        assert password_matches(db.get(Customer, 'cus_source').password_hash, 'correct-horse-test-only')
        assert db.get(License, 'lic_source').installation_id == 'installation1'
        assert db.get(CustomerToken, 'tokenhash').purpose == 'session'
    with pytest.raises(RuntimeError, match='empty initial database'):
        transfer(source, database_engine, confirm_maintenance=True)


def test_refuses_nonempty_target(source, database_engine):
    migrate(database_engine)
    with database_engine.begin() as target:
        target.execute(PaymentEvent.__table__.insert().values(id='existing', event_type='invoice.paid'))
    with pytest.raises(RuntimeError, match='contains data'):
        transfer(source, database_engine, confirm_maintenance=True)
    with database_engine.connect() as target:
        assert target.scalar(select(func.count()).select_from(Customer)) == 0
        assert target.scalar(select(func.count()).select_from(PaymentEvent)) == 1


def test_imports_legacy_version_one_without_trials(source, database_engine):
    from license_server.customer_models import CustomerTrial
    with source.begin() as db:
        CustomerTrial.__table__.drop(bind=db)
        db.execute(text('UPDATE bliss_schema_version SET version=1'))
    result = transfer(source, database_engine, confirm_maintenance=True)
    assert result['customer_trials'] == 0
    with database_engine.connect() as db:
        assert db.execute(text('SELECT version FROM bliss_schema_version')).scalar_one() == 2
        assert db.scalar(select(func.count()).select_from(Customer)) == 1


def test_failure_rolls_back_previously_inserted_rows(source, database_engine):
    # SQLite permits an overlength value that PostgreSQL correctly rejects.
    if database_engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL constraint rollback acceptance')
    with source.begin() as db:
        db.execute(PaymentEvent.__table__.update().values(event_type='x'*101))
    with pytest.raises(DataError):
        transfer(source, database_engine, confirm_maintenance=True)
    with database_engine.connect() as db:
        for table in Base.metadata.tables.values():
            assert db.scalar(select(func.count()).select_from(table)) == 0
        assert 'bliss_sqlite_import' not in inspect(db).get_table_names()


def test_requires_stopped_backend_confirmation(source, database_engine):
    with pytest.raises(RuntimeError, match='confirm maintenance'):
        transfer(source, database_engine)


def test_startup_requires_verified_import(source, database_engine):
    migrate(database_engine)
    with pytest.raises(RuntimeError, match='verified SQLite import'):
        require_import(database_engine)
    transfer(source, database_engine, confirm_maintenance=True)
    require_import(database_engine)
    migrate(database_engine)


def test_direct_application_start_cannot_bypass_import(source, database_engine, monkeypatch):
    from license_server import main
    monkeypatch.setattr(main, 'engine', database_engine)
    monkeypatch.setattr(main, 'settings', Settings(app_env='production', require_sqlite_import=True))
    migrate(database_engine)
    with pytest.raises(RuntimeError, match='verified SQLite import'):
        main.startup()
    transfer(source, database_engine, confirm_maintenance=True)
    main.startup()


def test_refuses_unknown_source_schema(source, database_engine):
    with source.begin() as db:
        db.execute(text('CREATE TABLE unknown_data (value TEXT)'))
    with pytest.raises(RuntimeError, match='Source schema differs'):
        transfer(source, database_engine, confirm_maintenance=True)


def test_password_file_handles_url_special_characters(tmp_path):
    file = tmp_path / 'password'
    file.write_text('test:@/#+?password\n')
    config = Settings(database_url='postgresql+psycopg://bliss_app@postgres/bliss_license',
                      database_password_file=str(file))
    assert database_url(config).password == 'test:@/#+?password'
