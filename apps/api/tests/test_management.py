from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, require_admin_principal, require_staff_principal
from app.db import Base, get_db
from app.dependencies import get_multiotp_adapter
from app.main import app
from app.multiotp import MockMultiOtpAdapter


engine = create_engine(
    "sqlite+pysqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(bind=engine)


def override_db() -> Generator[Session, None, None]:
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


adapter = MockMultiOtpAdapter()

app.dependency_overrides[get_db] = override_db
app.dependency_overrides[get_multiotp_adapter] = lambda: adapter
test_principal = Principal(
    subject="test-admin",
    email="test@example.com",
    groups=frozenset({"bliss-mfa-super-admin"}),
    bootstrap=True,
)
app.dependency_overrides[require_staff_principal] = lambda: test_principal
app.dependency_overrides[require_admin_principal] = lambda: test_principal

client = TestClient(app)


def test_user_enrollment_lifecycle() -> None:
    org_response = client.post(
        "/v1/organizations",
        json={"name": "Acme Test", "slug": "acme-test", "seat_limit": 5},
    )
    assert org_response.status_code == 201
    organization_id = org_response.json()["id"]

    user_response = client.post(
        f"/v1/organizations/{organization_id}/users",
        json={
            "username": "alice",
            "display_name": "Alice",
            "email": "alice@example.com",
        },
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["id"]

    enrollment_response = client.post(
        f"/v1/organizations/{organization_id}/users/{user_id}/enrollments"
    )
    assert enrollment_response.status_code == 201
    enrollment = enrollment_response.json()
    assert enrollment["provisioning_uri"].startswith("otpauth://")

    verify_response = client.post(
        "/v1/enrollments/verify",
        json={
            "enrollment_token": enrollment["enrollment_token"],
            "otp": "000000",
        },
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["verified"] is True

    revoke_response = client.post(
        f"/v1/organizations/{organization_id}/users/{user_id}/revoke",
        json={"reason": "Test device replacement"},
    )
    assert revoke_response.status_code == 204
