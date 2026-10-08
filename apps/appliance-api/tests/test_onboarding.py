import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from appliance import main
from appliance.db import Base, get_db
from appliance.models import AdminRole, MfaUser, UserStatus
from appliance.security import Principal, current_principal


@pytest.fixture
def kit(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    license = {'state': 'active'}
    class Agent:
        def status(self):
            return license
    monkeypatch.setattr(main, 'license_agent', Agent)
    principal = Principal(id='owner-test', email='owner@example.com', role=AdminRole.owner)
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[current_principal] = lambda: principal
    yield TestClient(main.app), db, license
    main.app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def test_completion_requires_enrollment_and_owner_confirmation(kit):
    client, db, _license = kit
    assert client.get('/v1/onboarding').json()['complete'] is False
    user = MfaUser(username='example', engine_username='example', status=UserStatus.pending)
    db.add(user)
    db.commit()
    assert client.post(f'/v1/onboarding/rdp/{user.id}').status_code == 409
    user.status = UserStatus.active
    db.commit()
    assert client.get('/v1/onboarding').json()['complete'] is False
    assert client.post(f'/v1/onboarding/rdp/{user.id}').status_code == 200
    assert client.get('/v1/onboarding').json()['complete'] is True
    user.status = UserStatus.revoked
    db.commit()
    assert client.get('/v1/onboarding').json()['complete'] is False


def test_restricted_license_cannot_complete_onboarding(kit):
    client, db, _license = kit
    user = MfaUser(username='example', engine_username='example', status=UserStatus.active)
    db.add(user)
    db.commit()
    _license['state'] = 'restricted'
    assert client.post(f'/v1/onboarding/rdp/{user.id}').status_code == 403
    assert client.get('/v1/onboarding').json()['complete'] is False


def test_operator_cannot_confirm_owner_acceptance(kit):
    client, _, _ = kit
    main.app.dependency_overrides[current_principal] = lambda: Principal(
        id='operator-test', email='operator@example.com', role=AdminRole.operator)
    assert client.post('/v1/onboarding/rdp/example').status_code == 403


def test_windows_account_discovery_is_read_only_and_marks_enrolled_accounts(kit, monkeypatch):
    import json
    import subprocess

    client, db, _ = kit
    db.add(MfaUser(username='jsmith', engine_username='jsmith', status=UserStatus.pending))
    db.commit()
    monkeypatch.setattr(main.os, 'name', 'nt')
    monkeypatch.setattr(main.subprocess, 'run', lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], 0, json.dumps([
            {'username': 'jsmith', 'display_name': 'John Smith', 'enabled': True},
            {'username': 'disabled', 'display_name': None, 'enabled': False},
        ]), ''))
    result = client.get('/v1/windows-users')
    assert result.status_code == 200
    user_id = db.query(MfaUser).one().id
    # A pending record is reported as "pending", never as enrolled (QR enrollment not verified).
    assert result.json() == [
        {'username': 'jsmith', 'display_name': 'John Smith', 'enabled': True,
         'mfa_user_id': user_id, 'mfa_status': 'pending', 'state': 'pending'},
        {'username': 'disabled', 'display_name': None, 'enabled': False,
         'mfa_user_id': None, 'mfa_status': None, 'state': 'disabled_account'},
    ]
    assert len(list(db.query(MfaUser))) == 1


def test_windows_account_discovery_refuses_non_windows_host(kit, monkeypatch):
    client, _, _ = kit
    monkeypatch.setattr(main.os, 'name', 'posix')
    assert client.get('/v1/windows-users').status_code == 503
