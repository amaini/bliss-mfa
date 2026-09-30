from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import timedelta, timezone

import stripe
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .crypto import canonical_json, iso, sign_payload
from .db import Base, engine, get_db
from .models import ActivationEvent, Challenge, License, LicenseStatus, LicenseType, utcnow
from .schemas import (
    ActivateOnlineRequest,
    BillingPortalRequest,
    BillingPortalResponse,
    ChallengeRequest,
    ChallengeResponse,
    HeartbeatRequest,
    LeaseResponse,
    LicenseCreate,
    LicenseCreated,
    LicenseStatusRead,
    OfflineIssueRequest,
    OfflineReleaseCode,
    ReleaseRequest,
    StripeLinkRequest,
)
from .security import require_admin
from .customer_routes import router as customer_router


settings = get_settings()
app = FastAPI(title="Bliss Secure MFA License Server", version="0.1.0")
app.include_router(customer_router)


@app.on_event("startup")
def startup() -> None:
    if settings.app_env == "development":
        Base.metadata.create_all(bind=engine)


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def activation_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def event(
    db: Session,
    license: License,
    event_type: str,
    installation_id: str | None = None,
    detail: str | None = None,
) -> None:
    db.add(
        ActivationEvent(
            license_id=license.id,
            installation_id=installation_id,
            event_type=event_type,
            detail=detail,
        )
    )


def new_activation_code() -> str:
    raw = secrets.token_urlsafe(24).replace("-", "").replace("_", "").upper()
    return f"BLS-{raw[:8]}-{raw[8:16]}-{raw[16:24]}-{raw[24:32]}"


def lease_for(license: License, *, offline: bool = False) -> LeaseResponse:
    now = utcnow()
    if offline:
        if not license.offline_expires_at:
            raise HTTPException(status_code=409, detail="Offline expiry is not configured")
        lease_expires = license.offline_expires_at
        grace_expires = None
    else:
        lease_expires = now + timedelta(days=settings.online_lease_days)
        grace_expires = now + timedelta(days=settings.online_grace_days)

    payload = {
        "v": 1,
        "license_id": license.id,
        "license_type": license.license_type.value,
        "installation_id": license.installation_id,
        "state": license.status.value,
        "max_rdp_users": license.max_rdp_users,
        "issued_at": iso(now),
        "lease_expires_at": iso(lease_expires),
        "grace_expires_at": iso(grace_expires) if grace_expires else None,
        "features": {
            "rdp_mfa": True,
            "local_admin": True,
            "audit": True,
            "device_recovery": True,
        },
    }
    return LeaseResponse(
        signed_lease=sign_payload(payload),
        state=license.status.value,
        max_rdp_users=license.max_rdp_users,
        lease_expires_at=lease_expires,
        grace_expires_at=grace_expires,
    )


def verify_installation_signature(
    license: License,
    signature: str,
    message: dict,
) -> None:
    if not license.installation_public_key:
        raise HTTPException(status_code=409, detail="Installation key is not registered")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            b64url_decode(license.installation_public_key)
        )
        public_key.verify(b64url_decode(signature), canonical_json(message))
    except (ValueError, InvalidSignature) as exc:
        raise HTTPException(status_code=401, detail="Invalid installation signature") from exc


def get_active_challenge(
    db: Session,
    installation_id: str,
    nonce: str,
) -> Challenge:
    row = db.get(Challenge, activation_hash(nonce))
    if not row or row.installation_id != installation_id or row.used_at is not None:
        raise HTTPException(status_code=401, detail="Invalid challenge")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < utcnow():
        raise HTTPException(status_code=401, detail="Challenge expired")
    return row


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/v1/admin/licenses",
    response_model=LicenseCreated,
    dependencies=[Depends(require_admin)],
)
def create_license(payload: LicenseCreate, db: Session = Depends(get_db)) -> LicenseCreated:
    code = new_activation_code()
    license_type = LicenseType(payload.license_type)
    offline_validity_days = None
    if license_type == LicenseType.offline:
        offline_validity_days = payload.offline_days or settings.offline_default_days

    license = License(
        customer_name=payload.customer_name,
        customer_email=str(payload.customer_email) if payload.customer_email else None,
        license_type=license_type,
        max_rdp_users=payload.max_rdp_users,
        activation_code_hash=activation_hash(code),
        offline_validity_days=offline_validity_days,
    )
    db.add(license)
    db.flush()
    event(db, license, "license.created")
    db.commit()
    return LicenseCreated(
        license_id=license.id,
        activation_code=code,
        license_type=license.license_type.value,
        max_rdp_users=license.max_rdp_users,
    )


@app.get(
    "/v1/admin/licenses",
    response_model=list[LicenseStatusRead],
    dependencies=[Depends(require_admin)],
)
def list_licenses(db: Session = Depends(get_db)) -> list[LicenseStatusRead]:
    licenses = list(db.scalars(select(License).order_by(License.customer_name)))
    return [
        LicenseStatusRead(
            id=item.id,
            customer_name=item.customer_name,
            license_type=item.license_type.value,
            status=item.status.value,
            max_rdp_users=item.max_rdp_users,
            installation_id=item.installation_id,
            last_seen_at=item.last_seen_at,
            last_reported_seats=item.last_reported_seats,
            offline_expires_at=item.offline_expires_at,
        )
        for item in licenses
    ]


@app.get(
    "/v1/admin/licenses/{license_id}",
    response_model=LicenseStatusRead,
    dependencies=[Depends(require_admin)],
)
def read_license(license_id: str, db: Session = Depends(get_db)) -> LicenseStatusRead:
    license = db.get(License, license_id)
    if not license:
        raise HTTPException(status_code=404, detail="License not found")
    return LicenseStatusRead(
        id=license.id,
        customer_name=license.customer_name,
        license_type=license.license_type.value,
        status=license.status.value,
        max_rdp_users=license.max_rdp_users,
        installation_id=license.installation_id,
        last_seen_at=license.last_seen_at,
        last_reported_seats=license.last_reported_seats,
        offline_expires_at=license.offline_expires_at,
    )


@app.post("/v1/activate/online", response_model=LeaseResponse)
def activate_online(payload: ActivateOnlineRequest, db: Session = Depends(get_db)) -> LeaseResponse:
    license = db.scalar(
        select(License).where(License.activation_code_hash == activation_hash(payload.activation_code))
    )
    if not license:
        raise HTTPException(status_code=401, detail="Invalid activation code")
    if license.license_type != LicenseType.online:
        raise HTTPException(status_code=409, detail="This license requires offline activation")
    if license.status != LicenseStatus.active:
        raise HTTPException(status_code=403, detail="License is not active")
    if license.installation_id and license.installation_id != payload.installation_id:
        raise HTTPException(status_code=409, detail="License is already bound to another installation")

    license.installation_id = payload.installation_id
    license.installation_public_key = payload.installation_public_key
    license.activation_code_hash = None
    license.last_seen_at = utcnow()
    event(db, license, "installation.activated", payload.installation_id)
    db.commit()
    return lease_for(license)


@app.post("/v1/challenges", response_model=ChallengeResponse)
def issue_challenge(payload: ChallengeRequest, db: Session = Depends(get_db)) -> ChallengeResponse:
    license = db.scalar(select(License).where(License.installation_id == payload.installation_id))
    if not license:
        raise HTTPException(status_code=404, detail="Installation not found")
    nonce = secrets.token_urlsafe(32)
    expires_at = utcnow() + timedelta(minutes=5)
    db.add(
        Challenge(
            nonce_hash=activation_hash(nonce),
            installation_id=payload.installation_id,
            expires_at=expires_at,
        )
    )
    db.commit()
    return ChallengeResponse(nonce=nonce, expires_at=expires_at)


@app.post("/v1/heartbeat", response_model=LeaseResponse)
def heartbeat(payload: HeartbeatRequest, db: Session = Depends(get_db)) -> LeaseResponse:
    license = db.scalar(select(License).where(License.installation_id == payload.installation_id))
    if not license:
        raise HTTPException(status_code=404, detail="Installation not found")
    if license.license_type != LicenseType.online:
        raise HTTPException(status_code=409, detail="Offline license does not use heartbeat")
    challenge = get_active_challenge(db, payload.installation_id, payload.nonce)
    message = {
        "installation_id": payload.installation_id,
        "nonce": payload.nonce,
        "protected_rdp_users": payload.protected_rdp_users,
        "software_version": payload.software_version,
        "machine_fingerprint": payload.machine_fingerprint,
        "audit_head_hash": payload.audit_head_hash,
    }
    verify_installation_signature(license, payload.signature, message)
    challenge.used_at = utcnow()
    license.last_seen_at = utcnow()
    license.last_reported_seats = payload.protected_rdp_users
    if (
        license.last_machine_fingerprint
        and payload.machine_fingerprint
        and license.last_machine_fingerprint != payload.machine_fingerprint
    ):
        event(
            db,
            license,
            "installation.fingerprint_changed",
            payload.installation_id,
            detail=json.dumps(
                {
                    "previous": license.last_machine_fingerprint,
                    "current": payload.machine_fingerprint,
                },
                separators=(",", ":"),
            ),
        )
    license.last_machine_fingerprint = payload.machine_fingerprint
    license.last_audit_head_hash = payload.audit_head_hash
    license.last_software_version = payload.software_version
    if payload.protected_rdp_users > license.max_rdp_users:
        event(
            db,
            license,
            "license.seat_overage_reported",
            payload.installation_id,
            detail=f"{payload.protected_rdp_users}/{license.max_rdp_users}",
        )
    event(
        db,
        license,
        "license.heartbeat",
        payload.installation_id,
        detail=json.dumps(
            {
                "protected_rdp_users": payload.protected_rdp_users,
                "software_version": payload.software_version,
            },
            separators=(",", ":"),
        ),
    )
    db.commit()
    return lease_for(license)


@app.post("/v1/release")
def release_installation(payload: ReleaseRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    license = db.scalar(select(License).where(License.installation_id == payload.installation_id))
    if not license:
        raise HTTPException(status_code=404, detail="Installation not found")
    challenge = get_active_challenge(db, payload.installation_id, payload.nonce)
    message = {
        "installation_id": payload.installation_id,
        "nonce": payload.nonce,
        "action": "release",
    }
    verify_installation_signature(license, payload.signature, message)
    challenge.used_at = utcnow()
    old_installation = license.installation_id
    license.installation_id = None
    license.installation_public_key = None
    license.last_seen_at = None
    license.last_reported_seats = None
    code = new_activation_code()
    license.activation_code_hash = activation_hash(code)
    event(db, license, "installation.released", old_installation)
    db.commit()
    return {"status": "released", "replacement_activation_code": code}


@app.post(
    "/v1/admin/licenses/{license_id}/status/{new_status}",
    dependencies=[Depends(require_admin)],
)
def change_license_status(
    license_id: str,
    new_status: str,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    license = db.get(License, license_id)
    if not license:
        raise HTTPException(status_code=404, detail="License not found")
    try:
        license.status = LicenseStatus(new_status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid license status") from exc
    event(db, license, "license.status_changed", license.installation_id, new_status)
    db.commit()
    return {"license_id": license.id, "status": license.status.value}


@app.post(
    "/v1/admin/offline/release",
    dependencies=[Depends(require_admin)],
)
def release_offline_license(
    payload: OfflineReleaseCode,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        envelope = json.loads(b64url_decode(payload.release_code))
        message = envelope["message"]
        signature = str(envelope["signature"])
        license_id = str(message["license_id"])
        installation_id = str(message["installation_id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid offline release code") from exc

    license = db.get(License, license_id)
    if not license or license.license_type != LicenseType.offline:
        raise HTTPException(status_code=404, detail="Offline license not found")
    if license.installation_id != installation_id:
        raise HTTPException(status_code=409, detail="Release code does not match bound installation")
    if message.get("action") != "offline_release":
        raise HTTPException(status_code=400, detail="Invalid release action")

    verify_installation_signature(license, signature, message)

    old_installation = license.installation_id
    license.installation_id = None
    license.installation_public_key = None
    license.last_seen_at = None
    license.last_reported_seats = None
    code = new_activation_code()
    license.activation_code_hash = activation_hash(code)
    event(db, license, "offline.released", old_installation)
    db.commit()
    return {
        "status": "released",
        "replacement_activation_code": code,
    }


@app.post(
    "/v1/admin/licenses/{license_id}/force-release",
    dependencies=[Depends(require_admin)],
)
def force_release(license_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    license = db.get(License, license_id)
    if not license:
        raise HTTPException(status_code=404, detail="License not found")
    old_installation = license.installation_id
    license.installation_id = None
    license.installation_public_key = None
    license.last_seen_at = None
    license.last_reported_seats = None
    code = new_activation_code()
    license.activation_code_hash = activation_hash(code)
    event(db, license, "installation.force_released", old_installation)
    db.commit()
    return {"status": "released", "replacement_activation_code": code}


@app.post(
    "/v1/admin/offline/issue",
    response_model=LeaseResponse,
    dependencies=[Depends(require_admin)],
)
def issue_offline(payload: OfflineIssueRequest, db: Session = Depends(get_db)) -> LeaseResponse:
    try:
        request_data = json.loads(b64url_decode(payload.installation_code))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid installation code") from exc

    code = str(request_data.get("activation_code", ""))
    installation_id = str(request_data.get("installation_id", ""))
    public_key = str(request_data.get("installation_public_key", ""))
    license = db.scalar(
        select(License).where(License.activation_code_hash == activation_hash(code))
    )
    if not license or license.license_type != LicenseType.offline:
        raise HTTPException(status_code=401, detail="Invalid offline activation")

    if license.installation_id and license.installation_id != installation_id:
        raise HTTPException(status_code=409, detail="License is already bound to another installation")

    if payload.max_rdp_users is not None:
        license.max_rdp_users = payload.max_rdp_users
    validity_days = (
        payload.validity_days
        or license.offline_validity_days
        or settings.offline_default_days
    )
    license.offline_validity_days = validity_days
    license.offline_expires_at = utcnow() + timedelta(days=validity_days)

    license.installation_id = installation_id
    license.installation_public_key = public_key
    license.activation_code_hash = None
    event(db, license, "offline.activated", installation_id)
    db.commit()
    return lease_for(license, offline=True)


@app.post("/v1/billing/portal", response_model=BillingPortalResponse)
def billing_portal(
    payload: BillingPortalRequest,
    db: Session = Depends(get_db),
) -> BillingPortalResponse:
    license = db.scalar(select(License).where(License.installation_id == payload.installation_id))
    if not license:
        raise HTTPException(status_code=404, detail="Installation not found")
    if not settings.stripe_secret_key or not license.stripe_customer_id:
        raise HTTPException(status_code=503, detail="Billing portal is not configured")
    challenge = get_active_challenge(db, payload.installation_id, payload.nonce)
    verify_installation_signature(license, payload.signature, {
        "installation_id": payload.installation_id, "nonce": payload.nonce, "action": "billing",
    })
    challenge.used_at = utcnow()
    db.commit()
    session = stripe.billing_portal.Session.create(
        customer=license.stripe_customer_id,
        return_url=settings.stripe_return_url,
        api_key=settings.stripe_secret_key,
    )
    return BillingPortalResponse(url=session["url"])


@app.post(
    "/v1/admin/licenses/{license_id}/stripe",
    dependencies=[Depends(require_admin)],
)
def link_stripe_customer(
    license_id: str,
    payload: StripeLinkRequest,
    db: Session = Depends(get_db),
) -> dict[str, str | None]:
    license = db.get(License, license_id)
    if not license:
        raise HTTPException(status_code=404, detail="License not found")
    license.stripe_customer_id = payload.customer_id
    license.stripe_subscription_id = payload.subscription_id
    event(db, license, "billing.stripe_linked", license.installation_id)
    db.commit()
    return {
        "license_id": license.id,
        "stripe_customer_id": license.stripe_customer_id,
        "stripe_subscription_id": license.stripe_subscription_id,
    }


@app.post(
    "/v1/admin/licenses/{license_id}/seats/{max_rdp_users}",
    dependencies=[Depends(require_admin)],
)
def change_seats(
    license_id: str,
    max_rdp_users: int,
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    if max_rdp_users < 1 or max_rdp_users > 100000:
        raise HTTPException(status_code=422, detail="Invalid RDP seat count")
    license = db.get(License, license_id)
    if not license:
        raise HTTPException(status_code=404, detail="License not found")
    license.max_rdp_users = max_rdp_users
    event(db, license, "license.seats_changed", license.installation_id, str(max_rdp_users))
    db.commit()
    return {"license_id": license.id, "max_rdp_users": license.max_rdp_users}
