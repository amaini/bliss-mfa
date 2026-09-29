import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..config import get_settings
from ..db import get_db
from ..dependencies import get_multiotp_adapter
from ..models import (
    DeviceStatus,
    Enrollment,
    EnrollmentStatus,
    MfaDevice,
    MfaUser,
    UserStatus,
    utcnow,
)
from ..multiotp import MultiOtpAdapter
from ..schemas import (
    EnrollmentStartRead,
    EnrollmentVerifyRead,
    EnrollmentVerifyRequest,
    RevokeDeviceRequest,
)
from ..security import require_bootstrap_admin


router = APIRouter(tags=["enrollment"])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_user_or_404(db: Session, organization_id: str, user_id: str) -> MfaUser:
    user = db.scalar(
        select(MfaUser).where(
            MfaUser.id == user_id,
            MfaUser.organization_id == organization_id,
        )
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post(
    "/organizations/{organization_id}/users/{user_id}/enrollments",
    response_model=EnrollmentStartRead,
    status_code=status.HTTP_201_CREATED,
)
def start_enrollment(
    organization_id: str,
    user_id: str,
    request: Request,
    actor_id: str = Depends(require_bootstrap_admin),
    db: Session = Depends(get_db),
    adapter: MultiOtpAdapter = Depends(get_multiotp_adapter),
) -> EnrollmentStartRead:
    user = get_user_or_404(db, organization_id, user_id)

    raw_token = secrets.token_urlsafe(48)
    settings = get_settings()
    expires_at = utcnow() + timedelta(minutes=settings.enrollment_ttl_minutes)

    device = MfaDevice(user_id=user.id, status=DeviceStatus.pending)
    db.add(device)
    db.flush()

    enrollment = Enrollment(
        user_id=user.id,
        device_id=device.id,
        token_hash=hash_token(raw_token),
        status=EnrollmentStatus.pending,
        expires_at=expires_at,
    )
    db.add(enrollment)

    try:
        provisioning = adapter.begin_enrollment(user.multiotp_username)
    except KeyError as exc:
        raise HTTPException(status_code=502, detail="MFA engine user is missing") from exc

    write_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="mfa.enrollment.started",
        subject_type="mfa_user",
        subject_id=user.id,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()

    return EnrollmentStartRead(
        enrollment_token=raw_token,
        provisioning_uri=provisioning.provisioning_uri,
        expires_at=expires_at,
    )


@router.post("/enrollments/verify", response_model=EnrollmentVerifyRead)
def verify_enrollment(
    payload: EnrollmentVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    adapter: MultiOtpAdapter = Depends(get_multiotp_adapter),
) -> EnrollmentVerifyRead:
    enrollment = db.scalar(
        select(Enrollment).where(Enrollment.token_hash == hash_token(payload.enrollment_token))
    )
    if not enrollment or enrollment.status != EnrollmentStatus.pending:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    now = utcnow()
    if enrollment.expires_at < now:
        enrollment.status = EnrollmentStatus.expired
        db.commit()
        raise HTTPException(status_code=410, detail="Enrollment expired")

    user = db.get(MfaUser, enrollment.user_id)
    device = db.get(MfaDevice, enrollment.device_id) if enrollment.device_id else None
    if not user or not device:
        raise HTTPException(status_code=409, detail="Enrollment state is incomplete")

    if not adapter.verify_otp(user.multiotp_username, payload.otp):
        write_audit(
            db,
            organization_id=user.organization_id,
            actor_id=user.id,
            actor_type="end_user",
            action="mfa.enrollment.verify_failed",
            subject_type="mfa_user",
            subject_id=user.id,
            success=False,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid one-time code")

    enrollment.status = EnrollmentStatus.verified
    enrollment.verified_at = now
    device.status = DeviceStatus.active
    device.enrolled_at = now
    user.status = UserStatus.active

    write_audit(
        db,
        organization_id=user.organization_id,
        actor_id=user.id,
        actor_type="end_user",
        action="mfa.enrollment.verified",
        subject_type="mfa_device",
        subject_id=device.id,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()

    return EnrollmentVerifyRead(verified=True, user_id=user.id, device_id=device.id)


@router.post(
    "/organizations/{organization_id}/users/{user_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_user_token(
    organization_id: str,
    user_id: str,
    payload: RevokeDeviceRequest,
    request: Request,
    actor_id: str = Depends(require_bootstrap_admin),
    db: Session = Depends(get_db),
    adapter: MultiOtpAdapter = Depends(get_multiotp_adapter),
) -> None:
    user = get_user_or_404(db, organization_id, user_id)
    adapter.revoke_token(user.multiotp_username)

    devices = list(
        db.scalars(
            select(MfaDevice).where(
                MfaDevice.user_id == user.id,
                MfaDevice.status == DeviceStatus.active,
            )
        )
    )
    now = utcnow()
    for device in devices:
        device.status = DeviceStatus.revoked
        device.revoked_at = now

    user.status = UserStatus.pending
    write_audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        action="mfa.device.revoked",
        subject_type="mfa_user",
        subject_id=user.id,
        reason=payload.reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
