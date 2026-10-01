"""Initial schema migration for a clean hosted prototype database.

Refuses unversioned existing databases: adopt them explicitly after backup and
schema inspection, rather than silently treating create_all as an upgrade.
"""
from sqlalchemy import inspect, text

from . import customer_models, models  # noqa: F401
from .db import Base, engine


def migrate(database=engine):
    tables = set(inspect(database).get_table_names())
    with database.begin() as connection:
        if tables and 'bliss_schema_version' not in tables:
            raise RuntimeError('Existing unversioned database needs explicit migration after backup')
        if 'bliss_schema_version' in tables:
            version = connection.execute(text('SELECT version FROM bliss_schema_version')).scalar_one()
            if version != 1:
                raise RuntimeError('Unsupported database schema version')
            missing = set(Base.metadata.tables) - tables
            if missing:
                raise RuntimeError('Versioned database is missing required tables')
            return
        Base.metadata.create_all(bind=connection)
        connection.execute(text('CREATE TABLE bliss_schema_version (version INTEGER NOT NULL)'))
        connection.execute(text('INSERT INTO bliss_schema_version (version) VALUES (1)'))


if __name__ == '__main__':
    migrate()
    print('Licensing database schema version 1 ready')
