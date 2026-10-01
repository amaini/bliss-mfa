"""Initial schema migration for a clean hosted prototype database.

Refuses unversioned existing databases: adopt them explicitly after backup and
schema inspection, rather than silently treating create_all as an upgrade.
"""
from sqlalchemy import inspect, text

from . import customer_models, models  # noqa: F401
from .db import Base, engine


def migrate(database=engine):
    with database.begin() as connection:
        if database.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(62418392)'))
        tables = set(inspect(connection).get_table_names())
        if tables and 'bliss_schema_version' not in tables:
            raise RuntimeError('Existing unversioned database needs explicit migration after backup')
        if 'bliss_schema_version' in tables:
            version = connection.execute(text('SELECT version FROM bliss_schema_version')).scalar_one()
            if version not in (1, 2):
                raise RuntimeError('Unsupported database schema version')
            missing = set(Base.metadata.tables) - tables
            if version == 1 and missing == {'customer_trials'}:
                customer_models.CustomerTrial.__table__.create(bind=connection)
                connection.execute(text('UPDATE bliss_schema_version SET version = 2'))
                return
            if version == 1 and not missing:
                raise RuntimeError('Version 1 unexpectedly contains version 2 tables')
            if missing:
                raise RuntimeError('Versioned database is missing required tables')
            return
        Base.metadata.create_all(bind=connection)
        connection.execute(text('CREATE TABLE bliss_schema_version (version INTEGER NOT NULL)'))
        connection.execute(text('INSERT INTO bliss_schema_version (version) VALUES (2)'))


def require_import(database=engine):
    if 'bliss_sqlite_import' not in inspect(database).get_table_names():
        raise RuntimeError('Backend withheld: verified SQLite import is required')
    with database.connect() as connection:
        if connection.execute(text('SELECT completed FROM bliss_sqlite_import')).scalar_one() != 1:
            raise RuntimeError('Backend withheld: invalid import marker')


if __name__ == '__main__':
    migrate()
    from .config import get_settings
    if get_settings().require_sqlite_import:
        require_import()
    print('Licensing database schema version 2 ready')
