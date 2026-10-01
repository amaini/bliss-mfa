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
