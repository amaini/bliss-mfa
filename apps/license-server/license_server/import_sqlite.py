"""Offline, transactional SQLite-to-PostgreSQL account/license transfer.

Run against a stopped backend's protected SQLite snapshot. Never prints rows,
passwords, tokens, connection URLs, or driver exception messages.
"""
import argparse
import enum
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select, text

from .db import Base, engine
from .migrate import migrate


def normal(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return value


def digest_rows(connection, table):
    digest = hashlib.sha256()
    count = 0
    for row in connection.execute(select(table).order_by(*table.primary_key.columns)).mappings():
        def serial(value):
            if isinstance(value, datetime):
                return normal(value).astimezone(UTC).isoformat()
            if isinstance(value, enum.Enum):
                return value.value
            raise TypeError('Unsupported database value')
        digest.update(json.dumps(dict(row), sort_keys=True, default=serial,
                                 separators=(',', ':')).encode())
        digest.update(b'\n')
        count += 1
    return count, digest.digest()


def validate_source(source):
    tables = set(inspect(source).get_table_names())
    version = source.execute(text('SELECT version FROM bliss_schema_version')).scalar_one() if 'bliss_schema_version' in tables else None
    expected = set(Base.metadata.tables) | {'bliss_schema_version'}
    if version == 1:
        expected -= {'customer_trials'}
    if tables != expected:
        raise RuntimeError('Source schema differs from its declared version; explicit review required')
    if version not in (1, 2):
        raise RuntimeError('Unsupported source schema version')
    if source.execute(text('PRAGMA integrity_check')).scalar_one() != 'ok':
        raise RuntimeError('Source integrity check failed')
    if source.execute(text('PRAGMA foreign_key_check')).first() is not None:
        raise RuntimeError('Source foreign-key check failed')
    for name, table in Base.metadata.tables.items():
        if name not in tables:
            continue
        columns = {c['name'] for c in inspect(source).get_columns(name)}
        if columns != set(table.columns.keys()):
            raise RuntimeError('Source columns differ in ' + name)


def transfer(source_engine, target_engine, *, confirm_maintenance=False):
    if not confirm_maintenance:
        raise RuntimeError('Stop backend writes and confirm maintenance before importing')
    if source_engine.dialect.name != 'sqlite':
        raise RuntimeError('Source must be SQLite')
    with source_engine.connect() as source:
        # Hold a consistent source snapshot; the CLI also opens it read-only.
        source.exec_driver_sql('BEGIN')
        validate_source(source)
        migrate(target_engine)
        counts = {}
        with target_engine.begin() as target:
            if target_engine.dialect.name == 'postgresql':
                target.execute(text('SELECT pg_advisory_xact_lock(62418391)'))
            allowed = set(Base.metadata.tables) | {'bliss_schema_version'}
            if set(inspect(target).get_table_names()) != allowed:
                raise RuntimeError('Target schema is not an empty initial database')
            for table in Base.metadata.sorted_tables:
                if target.scalar(select(func.count()).select_from(table)):
                    raise RuntimeError('Target contains data; refusing overwrite')
            for table in Base.metadata.sorted_tables:
                batch = []
                if table.name not in inspect(source).get_table_names():
                    counts[table.name] = 0
                    continue
                for row in source.execute(select(table)).mappings():
                    batch.append({k: normal(v) for k, v in row.items()})
                    if len(batch) == 500:
                        target.execute(table.insert(), batch)
                        batch = []
                if batch:
                    target.execute(table.insert(), batch)
                before = digest_rows(source, table)
                after = digest_rows(target, table)
                if before != after:
                    raise RuntimeError('Transferred data verification failed in ' + table.name)
                counts[table.name] = before[0]
            target.execute(text('CREATE TABLE bliss_sqlite_import (completed INTEGER PRIMARY KEY)'))
            target.execute(text('INSERT INTO bliss_sqlite_import (completed) VALUES (1)'))
        return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--confirm-maintenance', action='store_true')
    args = parser.parse_args()
    if engine.dialect.name != 'postgresql':
        parser.error('Target DATABASE_URL must use postgresql+psycopg')
    path = args.source.resolve(strict=True)
    source = create_engine('sqlite+pysqlite://', creator=lambda: sqlite3.connect(
        path.as_uri() + '?mode=ro', uri=True))
    try:
        counts = transfer(source, engine, confirm_maintenance=args.confirm_maintenance)
        print(json.dumps({'verified': True, 'rows': counts}))
    except Exception as exc:  # noqa: BLE001 -- driver errors can embed private row values
        print('Import aborted; target row transaction rolled back (' + type(exc).__name__ + ').')
        raise SystemExit(1) from None
    finally:
        source.dispose()


if __name__ == '__main__':
    main()
