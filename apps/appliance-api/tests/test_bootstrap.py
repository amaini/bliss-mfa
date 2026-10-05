from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

from appliance import main
from appliance.db import Base, get_db
from appliance.models import LocalAdmin


def test_bootstrap_is_single_use_under_concurrent_requests(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'appliance.db'),
                           connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main.settings, 'setup_token', 'private-initial-setup-token')
    def database():
        with Session(engine) as db:
            yield db
    main.app.dependency_overrides[get_db] = database
    try:
        def initialize(index):
            # The schema above is initialized once; exercise concurrent requests,
            # without concurrently running the application's startup migration.
            client = TestClient(main.app)
            try:
                return client.post('/v1/auth/bootstrap', json={
                    'setup_token': 'private-initial-setup-token', 'email': f'owner{index}@example.com',
                    'password': 'a sufficiently long password'}).status_code
            finally:
                client.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(initialize, [1, 2]))
        assert sorted(statuses) == [201, 409]
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(LocalAdmin)) == 1
            db.execute(delete(LocalAdmin))
            db.commit()
        assert initialize(3) == 409
    finally:
        main.app.dependency_overrides.clear()
        engine.dispose()
