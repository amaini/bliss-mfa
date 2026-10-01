import hashlib
import hmac
import json
import re
import time

import pytest
import stripe
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from license_server import customer_routes, main
from license_server.config import get_settings
from license_server.customer_models import Customer, CustomerLicense, CustomerToken, PaymentEvent, Purchase
from license_server.db import Base, get_db
from license_server.models import License
from license_server.crypto import canonical_json
from license_server.main import b64url_decode

PASSWORD = "correct-horse-prototype-42"


@pytest.fixture
def kit(tmp_path, monkeypatch, database_engine):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DEVELOPMENT_MAIL_DIR", str(tmp_path / "mail"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_local_test")
    monkeypatch.setenv("STRIPE_RDP_PRICE_ID", "price_seat")
    monkeypatch.setenv("CUSTOMER_PORTAL_URL", "http://testserver")
    signing = Ed25519PrivateKey.generate()
    monkeypatch.setenv("SIGNING_PRIVATE_KEY_PEM", signing.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode())
    get_settings.cache_clear()
    monkeypatch.setattr(main, "settings", get_settings())
    engine = database_engine
    Base.metadata.create_all(engine)

    def database():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    main.app.dependency_overrides[get_db] = database
    customer_routes._attempts.clear()
    price = {"id": "price_seat", "active": True, "recurring": {"interval": "month", "interval_count": 1},
             "billing_scheme": "per_unit", "currency": "cad", "unit_amount": 500}
    monkeypatch.setattr(stripe.Price, "retrieve", lambda *args, **kwargs: price)
    state = {"session": None, "subscription": {"id": "sub_test", "customer": "cus_stripe", "status": "active",
              "latest_invoice": {"status": "paid"}, "items": {"data": [{"price": {"id": "price_seat"}, "quantity": 5}]}}}

    def create_checkout(**kwargs):
        state["session"] = {"id": "cs_test", "client_reference_id": kwargs["client_reference_id"],
                            "mode": "subscription", "status": "open", "payment_status": "unpaid",
                            "customer": "cus_stripe", "subscription": "sub_test", "url": "https://checkout.stripe.com/test"}
        return state["session"]

    monkeypatch.setattr(stripe.checkout.Session, "create", create_checkout)
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", lambda *args, **kwargs: state["session"])
    monkeypatch.setattr(stripe.Subscription, "retrieve", lambda *args, **kwargs: state["subscription"])
    monkeypatch.setattr(stripe.billing_portal.Session, "create", lambda **kwargs: {"url": "https://billing.stripe.com/test"})
    with TestClient(main.app) as client:
        yield client, engine, tmp_path, state
    main.app.dependency_overrides.clear()
    engine.dispose()
    get_settings.cache_clear()


def register(kit, email="owner@example.com"):
    client, _, root, _ = kit
    assert client.post("/v1/customer/register", json={"email": email, "password": PASSWORD, "company_name": "Test Office"}).status_code == 202
    message = sorted((root / "mail").glob("*.eml"), key=lambda p: p.stat().st_mtime_ns)[-1].read_text()
    # EmailMessage wraps long lines using quoted-printable.
    from email import policy
    from email.parser import Parser
    body = Parser(policy=policy.default).parsestr(message).get_content()
    token = re.search(r"#verify=([^\s]+)", body).group(1)
    return token


def account(kit, email="owner@example.com"):
    token = register(kit, email)
    client = kit[0]
    assert client.post("/v1/customer/verify", json={"token": token}).status_code == 200
    assert client.post("/v1/customer/login", json={"email": email, "password": PASSWORD}).status_code == 200


def purchase(kit):
    account(kit)
    assert kit[0].post("/v1/customer/checkout", json={"seats": 5}).status_code == 200


def webhook(kit, event_id="evt_checkout", kind="checkout.session.completed", object_id="cs_test"):
    payload = json.dumps({"id": event_id, "type": kind, "data": {"object": {"id": object_id}}}).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(b"whsec_local_test", timestamp.encode() + b"." + payload, hashlib.sha256).hexdigest()
    return kit[0].post("/v1/webhooks/stripe", content=payload,
                       headers={"Stripe-Signature": f"t={timestamp},v1={signature}"})


def paid(kit):
    kit[3]["session"].update(status="complete", payment_status="paid")
    assert webhook(kit).status_code == 200


def test_download_requires_paid_license_and_matching_release_hash(kit, monkeypatch):
    client, _, root, _ = kit
    assert client.get('/v1/customer/downloads/windows').status_code == 401
    purchase(kit)
    assert client.get('/v1/customer/downloads/windows').status_code == 403
    paid(kit)
    assert client.get('/v1/customer/downloads').json()['available'] is False
    release = root / 'windows.zip'
    release.write_bytes(b'validated installer archive')
    monkeypatch.setenv('APPLIANCE_RELEASE_FILE', str(release))
    monkeypatch.setenv('APPLIANCE_RELEASE_SHA256', hashlib.sha256(release.read_bytes()).hexdigest())
    get_settings.cache_clear()
    metadata = client.get('/v1/customer/downloads').json()
    assert metadata['available'] is True
    response = client.get(metadata['url'])
    assert response.status_code == 200
    assert response.content == release.read_bytes()
    assert response.headers['cache-control'] == 'private, no-store'
    release.write_bytes(b'corrupted installer')
    assert client.get('/v1/customer/downloads/windows').status_code == 503
    assert client.get('/v1/customer/downloads').status_code == 503


def test_verification_required_and_single_use(kit):
    token = register(kit)
    client = kit[0]
    assert client.post("/v1/customer/login", json={"email": "owner@example.com", "password": PASSWORD}).status_code == 403
    assert client.post("/v1/customer/verify", json={"token": token}).status_code == 200
    assert client.post("/v1/customer/verify", json={"token": token}).status_code == 401


def test_paid_purchase_fulfills_once_and_code_is_owned(kit):
    purchase(kit)
    paid(kit)
    assert webhook(kit).status_code == 200
    assert webhook(kit, "evt_duplicate_object").status_code == 200
    with Session(kit[1]) as db:
        assert db.scalar(select(func.count()).select_from(License)) == 1
        assert db.scalar(select(func.count()).select_from(CustomerLicense)) == 1
    client = kit[0]
    assert client.get("/v1/customer/me").json()["license"]["max_rdp_users"] == 5
    code = client.post("/v1/customer/activation-code").json()["activation_code"]
    assert code.startswith("BLS-")
    assert client.post("/v1/customer/billing").status_code == 200
    assert client.post("/v1/customer/logout").status_code == 200
    assert client.get("/v1/customer/me").status_code == 401
    account(kit, "other@example.com")
    assert client.post("/v1/customer/activation-code").status_code == 403
    assert client.post("/v1/customer/billing").status_code == 404
    assert client.post("/v1/customer/purchases/cs_test/refresh").status_code == 404


def test_unpaid_and_forged_webhooks_do_not_issue_license(kit):
    purchase(kit)
    client = kit[0]
    assert client.post("/v1/webhooks/stripe", json={"id": "fake"}).status_code == 400
    assert webhook(kit).status_code == 200
    assert client.get("/v1/customer/me").json()["license"] is None
    assert client.post("/v1/customer/activation-code").status_code == 403


def test_landing_page_recovers_without_webhook(kit):
    purchase(kit)
    kit[3]["session"].update(status="complete", payment_status="paid")
    assert kit[0].post("/v1/customer/purchases/cs_test/refresh").json()["status"] == "fulfilled"
    assert webhook(kit).status_code == 200
    with Session(kit[1]) as db:
        assert db.scalar(select(func.count()).select_from(License)) == 1


def test_mismatched_price_rolls_back_and_can_retry(kit):
    purchase(kit)
    kit[3]["session"].update(status="complete", payment_status="paid")
    kit[3]["subscription"]["items"]["data"][0]["price"]["id"] = "price_wrong"
    assert webhook(kit).status_code == 409
    with Session(kit[1]) as db:
        assert db.get(PaymentEvent, "evt_checkout") is None
        assert db.scalar(select(func.count()).select_from(License)) == 0
    kit[3]["subscription"]["items"]["data"][0]["price"]["id"] = "price_seat"
    assert webhook(kit).status_code == 200


def test_subscription_reconciles_current_state_not_event_order(kit):
    purchase(kit)
    paid(kit)
    kit[3]["subscription"].update(status="past_due", latest_invoice={"status": "open"})
    assert webhook(kit, "evt_past_due", "customer.subscription.updated", "sub_test").status_code == 200
    assert kit[0].get("/v1/customer/me").json()["license"]["status"] == "suspended"
    kit[3]["subscription"].update(status="active", latest_invoice={"status": "paid"})
    kit[3]["subscription"]["items"]["data"][0]["quantity"] = 8
    assert webhook(kit, "evt_old_deleted", "customer.subscription.deleted", "sub_test").status_code == 200
    license = kit[0].get("/v1/customer/me").json()["license"]
    assert license["status"] == "active" and license["max_rdp_users"] == 8


def test_bound_license_cannot_issue_new_activation_code(kit):
    purchase(kit)
    paid(kit)
    with Session(kit[1]) as db:
        license = db.scalar(select(License))
        license.installation_id = "MFA-bound-test"
        db.commit()
    assert kit[0].post("/v1/customer/activation-code").status_code == 409


def test_cross_origin_mutation_rejected(kit):
    assert kit[0].post("/v1/customer/register", json={}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_checkout_retry_reuses_pending_order(kit):
    purchase(kit)
    assert kit[0].post("/v1/customer/checkout", json={"seats": 10}).status_code == 200
    with Session(kit[1]) as db:
        assert db.scalar(select(func.count()).select_from(Purchase)) == 1


def test_password_reset_invalidates_sessions_and_is_single_use(kit):
    account(kit)
    client = kit[0]
    assert client.post("/v1/customer/forgot-password", json={"email": "owner@example.com"}).status_code == 202
    from email import policy
    from email.parser import Parser
    message = max((kit[2] / "mail").glob("*.eml"), key=lambda p: p.stat().st_mtime_ns).read_text()
    token = re.search(r"#reset=([^\s]+)", Parser(policy=policy.default).parsestr(message).get_content()).group(1)
    payload = {"token": token, "password": "new-password-prototype-42"}
    assert client.post("/v1/customer/reset-password", json=payload).status_code == 200
    assert client.get("/v1/customer/me").status_code == 401
    assert client.post("/v1/customer/reset-password", json=payload).status_code == 401
    assert client.post("/v1/customer/login", json={"email": "owner@example.com", "password": PASSWORD}).status_code == 401
    with Session(kit[1]) as db:
        assert db.scalar(select(func.count()).select_from(CustomerToken).where(CustomerToken.purpose == "session")) == 0
        assert db.scalar(select(Customer)).password_hash != payload["password"]


def test_unauthenticated_appliance_billing_requires_signature(kit):
    assert kit[0].post("/v1/billing/portal", json={"installation_id": "MFA-guessable"}).status_code == 422


def test_paid_customer_can_activate_and_billing_requires_device_proof(kit):
    import base64
    purchase(kit)
    paid(kit)
    client = kit[0]
    code = client.post("/v1/customer/activation-code").json()["activation_code"]
    device = Ed25519PrivateKey.generate()
    def encode(raw):
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")
    installation = "MFA-customer-installation"
    public_key = encode(device.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    response = client.post("/v1/activate/online", json={"activation_code": code,
        "installation_id": installation, "installation_public_key": public_key})
    assert response.status_code == 200
    envelope = json.loads(b64url_decode(response.json()["signed_lease"]))
    lease = json.loads(b64url_decode(envelope["payload"]))
    assert lease["installation_id"] == installation and lease["max_rdp_users"] == 5
    assert client.post("/v1/customer/activation-code").status_code == 409
    nonce = client.post("/v1/challenges", json={"installation_id": installation}).json()["nonce"]
    message = {"installation_id": installation, "nonce": nonce, "action": "billing"}
    request = {"installation_id": installation, "nonce": nonce,
               "signature": encode(device.sign(canonical_json(message)))}
    invalid = {**request, "signature": encode(Ed25519PrivateKey.generate().sign(canonical_json(message)))}
    assert client.post("/v1/billing/portal", json=invalid).status_code == 401
    assert client.post("/v1/billing/portal", json=request).status_code == 200
    assert client.post("/v1/billing/portal", json=request).status_code == 401


def test_public_page_is_available(kit):
    response = kit[0].get("/customer")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_signing_failure_preserves_activation_code(kit, monkeypatch):
    from license_server.models import ActivationEvent
    purchase(kit)
    paid(kit)
    client, engine, _, _ = kit
    code = client.post("/v1/customer/activation-code").json()["activation_code"]
    with Session(engine) as db:
        before = db.scalar(select(func.count()).select_from(ActivationEvent))
    original = main.lease_for
    def fail_signing(license, **kwargs):
        raise RuntimeError("Signing key unavailable")
    monkeypatch.setattr(main, "lease_for", fail_signing)
    payload = {"activation_code": code, "installation_id": "MFA-retry",
               "installation_public_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}
    with pytest.raises(RuntimeError, match="Signing key unavailable"):
        client.post("/v1/activate/online", json=payload)
    with Session(engine) as db:
        license = db.scalar(select(License))
        assert license.installation_id is None
        assert license.activation_code_hash == main.activation_hash(code)
        assert db.scalar(select(func.count()).select_from(ActivationEvent)) == before
    monkeypatch.setattr(main, "lease_for", original)
    assert client.post("/v1/activate/online", json=payload).status_code == 200


def test_trial_is_verified_one_time_and_downloads_without_payment(kit, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from license_server.customer_models import CustomerTrial
    client, engine, root, _ = kit
    assert client.post('/v1/customer/trial', json={}).status_code == 401
    register(kit)
    assert client.post('/v1/customer/login', json={'email':'owner@example.com','password':PASSWORD}).status_code == 403
    # Use another verified account because registration above intentionally remains unverified.
    account(kit, 'trial@example.com')
    before = datetime.now(timezone.utc)
    result = client.post('/v1/customer/trial', json={})
    assert result.status_code == 200
    end = datetime.fromisoformat(result.json()['expires_at'])
    assert before + timedelta(days=14) <= end <= datetime.now(timezone.utc) + timedelta(days=14)
    assert client.post('/v1/customer/trial', json={}).json()['expires_at'] == result.json()['expires_at']
    info = client.get('/v1/customer/me').json()
    assert info['trial_available'] is False
    assert info['license']['is_trial'] and info['license']['max_rdp_users'] == 1
    release = root / 'trial.zip'
    release.write_bytes(b'trial-installer-fixture')
    monkeypatch.setenv('APPLIANCE_RELEASE_FILE', str(release))
    monkeypatch.setenv('APPLIANCE_RELEASE_SHA256', hashlib.sha256(release.read_bytes()).hexdigest())
    get_settings.cache_clear()
    assert client.get('/v1/customer/downloads/windows').content == release.read_bytes()
    assert client.post('/v1/customer/activation-code', json={}).status_code == 200
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(CustomerTrial)) == 1
        assert db.scalar(select(func.count()).select_from(Purchase)) == 0


def test_trial_expiry_caps_signed_lease_and_cannot_be_restarted(kit):
    from datetime import timedelta
    from license_server.customer_models import CustomerTrial
    from license_server.models import utcnow
    client, engine, _, _ = kit
    account(kit)
    client.post('/v1/customer/trial', json={})
    code = client.post('/v1/customer/activation-code', json={}).json()['activation_code']
    response = client.post('/v1/activate/online', json={'activation_code':code,
        'installation_id':'MFA-trial-test','installation_public_key':'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'})
    assert response.status_code == 200
    envelope = json.loads(b64url_decode(response.json()['signed_lease']))
    payload = json.loads(b64url_decode(envelope['payload']))
    assert payload['lease_expires_at'] <= payload['trial_expires_at']
    assert payload['grace_expires_at'] <= payload['trial_expires_at']
    with Session(engine) as db:
        trial = db.scalar(select(CustomerTrial))
        trial.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        signed = main.lease_for(db.get(License, trial.license_id), db=db)
        assert signed.state == 'expired'
    assert client.get('/v1/customer/me').json()['license']['status'] == 'expired'
    assert client.post('/v1/customer/trial', json={}).status_code == 409
    assert client.post('/v1/customer/activation-code', json={}).status_code == 409
    assert client.get('/v1/customer/downloads').status_code == 403


@pytest.mark.parametrize('expired', [False, True])
def test_trial_upgrade_preserves_bound_appliance_and_removes_expiry(kit, expired):
    from datetime import timedelta
    from license_server.models import utcnow
    from license_server.customer_models import CustomerTrial
    client, engine, _, _ = kit
    account(kit)
    assert client.post('/v1/customer/trial', json={}).status_code == 200
    original = client.get('/v1/customer/me').json()['license']['id']
    with Session(engine) as db:
        license = db.get(License, original)
        license.installation_id = 'MFA-preserved-trial-device'
        license.installation_public_key = 'original-device-public-key'
        if expired:
            db.scalar(select(CustomerTrial)).expires_at = utcnow() - timedelta(days=1)
        db.commit()
    assert client.post('/v1/customer/checkout', json={'seats':5}).status_code == 200
    assert client.get('/v1/customer/me').json()['license']['is_trial'] is True
    paid(kit)
    info = client.get('/v1/customer/me').json()['license']
    assert info['id'] == original and info['installation_id'] == 'MFA-preserved-trial-device'
    assert info['max_rdp_users'] == 5 and info['is_trial'] is False
    with Session(engine) as db:
        license = db.get(License, original)
        assert license.installation_public_key == 'original-device-public-key'
        assert db.scalar(select(CustomerTrial)).converted_at is not None
        envelope = json.loads(b64url_decode(main.lease_for(license, db=db).signed_lease))
        assert json.loads(b64url_decode(envelope['payload']))['trial_expires_at'] is None
    assert client.post('/v1/customer/trial', json={}).status_code == 409


def test_cached_trial_is_restricted_at_deadline_without_contacting_server(kit, monkeypatch):
    from datetime import datetime, timedelta
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'services/license-agent'))
    from license_agent.config import get_settings as agent_settings
    from license_agent.state import LicenseState
    private = serialization.load_pem_private_key(main.settings.signing_private_key_pem.encode(), password=None)
    monkeypatch.setenv('BLISS_SIGNING_PUBLIC_KEY_PEM', private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())
    agent_settings.cache_clear()
    try:
        client, _, root, _ = kit
        state = LicenseState(str(root / 'trial-agent'))
        account(kit)
        end = datetime.fromisoformat(client.post('/v1/customer/trial', json={}).json()['expires_at'])
        code = client.post('/v1/customer/activation-code', json={}).json()['activation_code']
        response = client.post('/v1/activate/online', json={'activation_code':code,
            'installation_id':state.installation_id(), 'installation_public_key':state.public_key_b64()})
        state.save_lease(response.json()['signed_lease'])
        assert state.reserve_seat('first-user')['allowed']
        assert not state.reserve_seat('second-user')['allowed']
        monkeypatch.setattr(state, 'trusted_now', lambda: end + timedelta(seconds=1))
        assert state.effective_status()['state'] == 'restricted'
        assert not state.reserve_seat('third-user')['allowed']
    finally:
        agent_settings.cache_clear()
