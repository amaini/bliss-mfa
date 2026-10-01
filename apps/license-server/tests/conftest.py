import os
import uuid

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def database_engine(tmp_path):
    """Use a real isolated PostgreSQL schema when TEST_POSTGRES_URL is supplied."""
    url = os.environ.get('TEST_POSTGRES_URL')
    if not url:
        engine = create_engine('sqlite:///' + str(tmp_path / 'target.db'),
                               connect_args={'check_same_thread': False})
        yield engine
        engine.dispose()
        return
    admin = create_engine(url)
    schema = 'bliss_test_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text('CREATE SCHEMA ' + schema))
    engine = create_engine(url, connect_args={'options': '-csearch_path=' + schema})
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        admin.dispose()
