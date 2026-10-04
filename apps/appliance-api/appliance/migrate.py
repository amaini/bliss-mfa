"""Version the known appliance schema without silently repairing customer data."""
from sqlalchemy import inspect, text

from . import models  # noqa: F401
from .db import Base, engine

SCHEMA_VERSION = 1
VERSION_TABLE = "bliss_appliance_schema"


def _validate(connection):
    inspector = inspect(connection)
    required = set(Base.metadata.tables)
    actual = set(inspector.get_table_names()) - {VERSION_TABLE}
    if actual != required:
        raise RuntimeError("Appliance schema tables differ; restore or migrate explicitly")
    for name, table in Base.metadata.tables.items():
        columns = {column["name"]: column for column in inspector.get_columns(name)}
        if set(columns) != set(table.columns.keys()):
            raise RuntimeError(f"Appliance schema columns differ in {name}")
        for column in table.columns:
            found = columns[column.name]
            expected_type = column.type.compile(dialect=connection.dialect).upper()
            actual_type = found["type"].compile(dialect=connection.dialect).upper()
            if actual_type != expected_type or found["nullable"] != column.nullable:
                raise RuntimeError(f"Appliance schema column differs in {name}.{column.name}")
        expected_pk = [column.name for column in table.primary_key.columns]
        if inspector.get_pk_constraint(name)["constrained_columns"] != expected_pk:
            raise RuntimeError(f"Appliance primary key differs in {name}")
        unique = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints(name)
        }
        unique.update(
            tuple(item["column_names"])
            for item in inspector.get_indexes(name) if item["unique"]
        )
        for column in table.columns:
            if column.unique and (column.name,) not in unique:
                raise RuntimeError(f"Appliance uniqueness constraint missing in {name}")


def migrate(database=engine):
    """Initialize a clean database or seal the exact legacy schema at version 1.

    Legacy adoption changes only the version marker. No user, enrollment, owner
    seal or audit row is rewritten. Future schema changes require a migration.
    """
    with database.connect() as connection:
        # Serialize SQLite startup, including inspection and first-time creation.
        if database.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        elif database.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(62418393)"))
        else:
            raise RuntimeError("Unsupported appliance database dialect")
        try:
            tables = set(inspect(connection).get_table_names())
            if not tables:
                Base.metadata.create_all(bind=connection)
            else:
                if VERSION_TABLE in tables:
                    versions = connection.execute(
                        text(f"SELECT version FROM {VERSION_TABLE}")
                    ).scalars().all()
                    if versions != [SCHEMA_VERSION]:
                        raise RuntimeError("Unsupported appliance schema version")
                _validate(connection)
            if VERSION_TABLE not in tables:
                connection.execute(text(
                    f"CREATE TABLE {VERSION_TABLE} "
                    "(id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)"
                ))
                connection.execute(text(
                    f"INSERT INTO {VERSION_TABLE} (id, version) VALUES (1, :version)"
                ), {"version": SCHEMA_VERSION})
            connection.commit()
        except Exception:
            connection.rollback()
            raise


if __name__ == "__main__":
    migrate()
    print(f"Appliance schema version {SCHEMA_VERSION} ready")
