from __future__ import annotations

import hmac

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .audit import write_audit
from .clients import AdapterOperationError, LicenseAgentClient, MultiOtpClient
from .config import get_settings
from .db import Base, SessionLocal, engine, get_db
from .models import AdminRole, AuditEvent, BootstrapSeal, LocalAdmin, MfaUser, UserStatus, event_digest
from .schemas import (
    AdminCreate,
    AdminRead,
    AuditRead,
    BootstrapRequest,
    EnrollmentRead,
    LicenseActivate,
    LoginRequest,
    OfflineApply,
    ReasonRequest,
    ResyncRequest,
    TokenRead,
    UserCreate,
    UserRead,
    VerifyRequest,
)
from .security import (
    Principal,
    current_principal,
    hash_password,
    issue_token,
    require_admin,
    require_operator,
    require_owner,
    verify_password,
)

settings = get_settings()
scheduler = BackgroundScheduler(daemon=True)
app = FastAPI(title="Bliss Secure MFA Appliance API", version="0.1.0")


@app.get('/v1/onboarding')
def onboarding_status(
    _: Principal = Depends(current_principal), db: Session = Depends(get_db),
) -> dict:
    users = list(db.scalars(select(MfaUser).where(MfaUser.protected_rdp.is_(True))))
    active = [user for user in users if user.status == UserStatus.active]
    try:
        license = license_agent().status()
        licensed = license.get('state') in {'active', 'offline_grace'}
    except (httpx.HTTPError, RuntimeError):
        licensed = False
    confirmed = set(db.scalars(select(AuditEvent.subject_id).where(
        AuditEvent.action == 'onboarding.rdp.confirmed', AuditEvent.success.is_(True))))
    rdp_confirmed = any(user.id in confirmed for user in active)
    steps = [
        {'id': 'owner', 'title': 'Create your local administrator', 'complete': True, 'href': '/administrators'},
        {'id': 'license', 'title': 'Activate your paid license', 'complete': licensed, 'href': '/license'},
        {'id': 'user', 'title': 'Add your first Windows account', 'complete': bool(users), 'href': '/users'},
        {'id': 'authenticator', 'title': 'Enroll and verify an authenticator', 'complete': bool(active), 'href': '/users'},
        {'id': 'rdp', 'title': 'Test protected RDP access', 'complete': rdp_confirmed, 'href': '/onboarding'},
    ]
    return {'steps': steps, 'complete': all(step['complete'] for step in steps),
            'active_users': [{'id': user.id, 'username': user.username} for user in active]}


@app.post('/v1/onboarding/rdp/{user_id}')
def confirm_rdp_onboarding(
    user_id: str, request: Request, principal: Principal = Depends(require_owner),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(MfaUser, user_id)
    if not user or user.status != UserStatus.active or not user.protected_rdp:
        raise HTTPException(409, 'Enroll and verify a protected user before confirming RDP')
    try:
        licensed = license_agent().status().get('state') in {'active', 'offline_grace'}
    except (httpx.HTTPError, RuntimeError):
        raise HTTPException(503, 'License agent unavailable') from None
    if not licensed:
        raise HTTPException(403, 'Activate your license before confirming RDP')
    write_audit(db, actor_id=principal.id, action='onboarding.rdp.confirmed',
                subject_type='mfa_user', subject_id=user.id,
                reason='Owner confirms protected RDP sign-in and incorrect OTP rejection',
                source_ip=request.client.host if request.client else None)
    db.commit()
    return {'confirmed': True}


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


def multiotp() -> MultiOtpClient:
    return MultiOtpClient()


def license_agent() -> LicenseAgentClient:
    return LicenseAgentClient()


def protected_seat_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(MfaUser)
            .where(
                MfaUser.protected_rdp.is_(True),
                MfaUser.status.in_(
                    [UserStatus.pending, UserStatus.active, UserStatus.locked]
                ),
            )
        )
        or 0
    )


def automatic_license_heartbeat() -> None:
    db = SessionLocal()
    try:
        audit_head = db.scalar(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(1))
        license_agent().heartbeat(
            protected_seat_count(db),
            audit_head.event_hash if audit_head else None,
        )
    except (httpx.HTTPError, RuntimeError):
        # A network outage must not destroy the last valid signed lease.
        pass
    finally:
        db.close()


@app.on_event("startup")
def start_heartbeat_scheduler() -> None:
    if settings.app_env == "test" or settings.heartbeat_interval_hours <= 0:
        return
    scheduler.add_job(
        automatic_license_heartbeat,
        "interval",
        hours=settings.heartbeat_interval_hours,
        id="bliss-license-heartbeat",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()


@app.on_event("shutdown")
def stop_heartbeat_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def user_or_404(db: Session, user_id: str) -> MfaUser:
    user = db.get(MfaUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def reserve_user_seat(username: str) -> dict:
    try:
        result = license_agent().reserve_seat(username)
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="License agent unavailable") from exc
    if not result["allowed"]:
        raise HTTPException(status_code=403, detail=result.get("reason") or "License denied")
    return result


def release_user_seat_best_effort(username: str) -> None:
    try:
        license_agent().release_seat(username)
    except (httpx.HTTPError, RuntimeError):
        # Never prevent offboarding because the local licensing service is
        # temporarily unavailable. A stale reservation only over-enforces seats.
        pass


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/auth/bootstrap", response_model=TokenRead, status_code=201)
def bootstrap(payload: BootstrapRequest, db: Session = Depends(get_db)) -> TokenRead:
    if db.get(BootstrapSeal, 1) or db.scalar(select(func.count()).select_from(LocalAdmin)):
        raise HTTPException(status_code=409, detail="Appliance is already initialized")
    if not settings.setup_token or not hmac.compare_digest(payload.setup_token, settings.setup_token):
        raise HTTPException(status_code=401, detail="Invalid setup token")
    # The unique reservation serializes simultaneous first-time setup requests.
    # Keep the seal even if administrators are later removed through recovery.
    db.add(BootstrapSeal(id=1))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Appliance is already initialized') from None

    admin = LocalAdmin(
        email=str(payload.email).lower(),
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=AdminRole.owner,
    )
    db.add(admin)
    db.flush()
    write_audit(
        db,
        actor_id=admin.id,
        action="admin.bootstrap_created",
        subject_type="local_admin",
        subject_id=admin.id,
    )
    db.commit()
    return TokenRead(access_token=issue_token(admin))


@app.post("/v1/auth/login", response_model=TokenRead)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenRead:
    admin = db.scalar(
        select(LocalAdmin).where(LocalAdmin.email == str(payload.email).lower())
    )
    if not admin or admin.disabled or not verify_password(admin.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenRead(access_token=issue_token(admin))


@app.get("/v1/me")
def me(principal: Principal = Depends(current_principal)) -> dict[str, str]:
    return {
        "id": principal.id,
        "email": principal.email,
        "role": principal.role.value,
        "company_name": settings.company_name,
    }


@app.get("/v1/admins", response_model=list[AdminRead])
def list_admins(
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[LocalAdmin]:
    return list(db.scalars(select(LocalAdmin).order_by(LocalAdmin.email)))


@app.post("/v1/admins", response_model=AdminRead, status_code=201)
def create_admin(
    payload: AdminCreate,
    request: Request,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LocalAdmin:
    email = str(payload.email).lower()
    if db.scalar(select(LocalAdmin).where(LocalAdmin.email == email)):
        raise HTTPException(status_code=409, detail="Administrator already exists")
    if payload.role == AdminRole.owner.value and principal.role != AdminRole.owner:
        raise HTTPException(status_code=403, detail="Only the owner can create another owner")

    admin = LocalAdmin(
        email=email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=AdminRole(payload.role),
    )
    db.add(admin)
    db.flush()
    write_audit(
        db,
        actor_id=principal.id,
        action="admin.created",
        subject_type="local_admin",
        subject_id=admin.id,
        reason=f"role={admin.role.value}",
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(admin)
    return admin


@app.delete("/v1/admins/{admin_id}", status_code=204)
def delete_admin(
    admin_id: str,
    request: Request,
    reason: str,
    principal: Principal = Depends(require_owner),
    db: Session = Depends(get_db),
) -> None:
    admin = db.get(LocalAdmin, admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Administrator not found")
    if admin.id == principal.id:
        raise HTTPException(status_code=409, detail="Owner cannot delete the active account")

    if admin.role == AdminRole.owner:
        owners = int(
            db.scalar(
                select(func.count())
                .select_from(LocalAdmin)
                .where(LocalAdmin.role == AdminRole.owner, LocalAdmin.disabled.is_(False))
            )
            or 0
        )
        if owners <= 1:
            raise HTTPException(status_code=409, detail="The final owner cannot be removed")

    db.delete(admin)
    write_audit(
        db,
        actor_id=principal.id,
        action="admin.deleted",
        subject_type="local_admin",
        subject_id=admin_id,
        reason=reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()


@app.get("/v1/users", response_model=list[UserRead])
def list_users(
    _: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[MfaUser]:
    return list(db.scalars(select(MfaUser).order_by(MfaUser.username)))


@app.post("/v1/users", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> MfaUser:
    if db.scalar(select(MfaUser).where(MfaUser.username == payload.username)):
        raise HTTPException(status_code=409, detail="User already exists")

    seat = reserve_user_seat(payload.username)

    try:
        multiotp().create_user(payload.username)
    except (httpx.HTTPError, RuntimeError) as exc:
        if not seat.get("already_reserved"):
            release_user_seat_best_effort(payload.username)
        write_audit(
            db, actor_id=principal.id, action="mfa.user.create_failed",
            subject_type="mfa_user", subject_id=payload.username, success=False,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
        raise HTTPException(status_code=502, detail="Unable to create user in MFA engine") from exc

    user = MfaUser(
        username=payload.username,
        display_name=payload.display_name,
        email=str(payload.email) if payload.email else None,
        protected_rdp=True,
        engine_username=payload.username,
        status=UserStatus.pending,
    )
    db.add(user)
    db.flush()
    write_audit(
        db,
        actor_id=principal.id,
        action="mfa.user.created",
        subject_type="mfa_user",
        subject_id=user.id,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)
    return user


@app.post("/v1/users/{user_id}/enrollment", response_model=EnrollmentRead)
def enrollment(
    user_id: str,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> EnrollmentRead:
    user = user_or_404(db, user_id)
    if user.status != UserStatus.pending:
        raise HTTPException(status_code=409, detail="Only pending users may be enrolled")
    try:
        uri = multiotp().provisioning_uri(user.engine_username)
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail="Unable to obtain provisioning data") from exc
    return EnrollmentRead(provisioning_uri=uri)


@app.post("/v1/users/{user_id}/verify", response_model=UserRead)
def verify_enrollment(
    user_id: str,
    payload: VerifyRequest,
    request: Request,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> MfaUser:
    user = user_or_404(db, user_id)
    if user.status != UserStatus.pending:
        raise HTTPException(status_code=409, detail="User is not pending enrollment")
    try:
        ok = multiotp().verify(user.engine_username, payload.otp)
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail="MFA engine verification failed") from exc
    if not ok:
        write_audit(
            db,
            actor_id=principal.id,
            action="mfa.enrollment.verify_failed",
            subject_type="mfa_user",
            subject_id=user.id,
            success=False,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid one-time code")

    user.status = UserStatus.active
    write_audit(
        db,
        actor_id=principal.id,
        action="mfa.enrollment.verified",
        subject_type="mfa_user",
        subject_id=user.id,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)
    return user


def reason_command(
    *,
    user_id: str,
    command: str,
    action: str,
    new_status: UserStatus | None,
    payload: ReasonRequest,
    request: Request,
    principal: Principal,
    db: Session,
    requires_seat: bool = False,
) -> MfaUser:
    user = user_or_404(db, user_id)
    if command != "revoke" and user.status == UserStatus.revoked:
        raise HTTPException(status_code=409, detail="Revoked users must be deleted and enrolled again")
    if command == "unlock" and user.status in {UserStatus.disabled, UserStatus.pending}:
        raise HTTPException(status_code=409, detail="Only enrolled, enabled users may be unlocked")
    if command == "lock" and user.status not in {UserStatus.active, UserStatus.locked}:
        raise HTTPException(status_code=409, detail="Only enrolled, enabled users may be locked")
    seat = None
    if requires_seat and user.protected_rdp and user.status in {UserStatus.disabled, UserStatus.revoked}:
        seat = reserve_user_seat(user.username)
    try:
        ok = multiotp().command(user.engine_username, command)
    except AdapterOperationError as exc:
        if exc.authentication_disabled:
            # A failed revoke can already have disabled the engine identity.
            # Revoke remains closed to enable/unlock even if rotation failed.
            user.status = UserStatus.revoked if command == "revoke" else UserStatus.disabled
        write_audit(
            db, actor_id=principal.id, action=action + "_failed", subject_type="mfa_user",
            subject_id=user.id, reason=payload.reason, success=False,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
        if exc.authentication_disabled and user.protected_rdp:
            release_user_seat_best_effort(user.username)
        raise HTTPException(status_code=409, detail="MFA engine command failed; authentication is disabled") from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        if seat and not seat.get("already_reserved"):
            release_user_seat_best_effort(user.username)
        raise HTTPException(status_code=502, detail="MFA engine command failed") from exc
    if not ok:
        if seat and not seat.get("already_reserved"):
            release_user_seat_best_effort(user.username)
        raise HTTPException(status_code=409, detail="MFA engine rejected the command")
    if new_status:
        user.status = new_status
    release_after_commit = (
        new_status in {UserStatus.disabled, UserStatus.revoked} and user.protected_rdp
    )
    write_audit(
        db,
        actor_id=principal.id,
        action=action,
        subject_type="mfa_user",
        subject_id=user.id,
        reason=payload.reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)
    if release_after_commit:
        release_user_seat_best_effort(user.username)
    return user


@app.post("/v1/users/{user_id}/disable", response_model=UserRead)
def disable_user(
    user_id: str,
    payload: ReasonRequest,
    request: Request,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> MfaUser:
    return reason_command(
        user_id=user_id, command="disable", action="mfa.user.disabled",
        new_status=UserStatus.disabled, payload=payload, request=request,
        principal=principal, db=db,
    )


@app.post("/v1/users/{user_id}/enable", response_model=UserRead)
def enable_user(
    user_id: str,
    payload: ReasonRequest,
    request: Request,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> MfaUser:
    return reason_command(
        user_id=user_id, command="enable", action="mfa.user.enabled",
        new_status=UserStatus.active, payload=payload, request=request,
        principal=principal, db=db, requires_seat=True,
    )


@app.post("/v1/users/{user_id}/unlock", response_model=UserRead)
def unlock_user(
    user_id: str,
    payload: ReasonRequest,
    request: Request,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> MfaUser:
    return reason_command(
        user_id=user_id, command="unlock", action="mfa.user.unlocked",
        new_status=UserStatus.active, payload=payload, request=request,
        principal=principal, db=db,
    )


@app.post("/v1/users/{user_id}/lock", response_model=UserRead)
def lock_user(
    user_id: str,
    payload: ReasonRequest,
    request: Request,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> MfaUser:
    return reason_command(
        user_id=user_id, command="lock", action="mfa.user.locked",
        new_status=UserStatus.locked, payload=payload, request=request,
        principal=principal, db=db,
    )


@app.post("/v1/users/{user_id}/revoke", response_model=UserRead)
def revoke_user(
    user_id: str,
    payload: ReasonRequest,
    request: Request,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> MfaUser:
    return reason_command(
        user_id=user_id, command="revoke", action="mfa.user.revoked",
        new_status=UserStatus.revoked, payload=payload, request=request,
        principal=principal, db=db,
    )


@app.post("/v1/users/{user_id}/resync", response_model=UserRead)
def resync_user(
    user_id: str,
    payload: ResyncRequest,
    request: Request,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> MfaUser:
    user = user_or_404(db, user_id)
    try:
        ok = multiotp().command(
            user.engine_username,
            "resync",
            {"otp1": payload.otp1, "otp2": payload.otp2},
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail="MFA engine resync failed") from exc
    write_audit(
        db,
        actor_id=principal.id,
        action="mfa.user.resynced" if ok else "mfa.user.resync_failed",
        subject_type="mfa_user",
        subject_id=user.id,
        reason=payload.reason,
        success=ok,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    if not ok:
        raise HTTPException(status_code=400, detail="Token resync failed")
    return user


@app.delete("/v1/users/{user_id}", status_code=204)
def delete_user(
    user_id: str,
    reason: str,
    request: Request,
    principal: Principal = Depends(require_operator),
    db: Session = Depends(get_db),
) -> None:
    user = user_or_404(db, user_id)
    try:
        ok = multiotp().delete_user(user.engine_username)
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail="MFA engine delete failed") from exc
    if not ok:
        raise HTTPException(status_code=409, detail="MFA engine rejected deletion")
    release_after_commit = user.protected_rdp
    username_for_release = user.username
    db.delete(user)
    write_audit(
        db,
        actor_id=principal.id,
        action="mfa.user.deleted",
        subject_type="mfa_user",
        subject_id=user_id,
        reason=reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    if release_after_commit:
        release_user_seat_best_effort(username_for_release)


@app.get("/v1/audit", response_model=list[AuditRead])
def audit(
    limit: int = 200,
    _: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[AuditEvent]:
    limit = max(1, min(limit, 500))
    return list(
        db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit))
    )


@app.get("/v1/audit/integrity")
def audit_integrity(
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.asc())))
    previous_hash = None
    for index, event in enumerate(events):
        expected = event_digest(
            actor_id=event.actor_id,
            action=event.action,
            subject_type=event.subject_type,
            subject_id=event.subject_id,
            reason=event.reason,
            success=event.success,
            previous_hash=previous_hash,
            created_at=event.created_at,
        )
        if event.previous_hash != previous_hash or event.event_hash != expected:
            return {
                "valid": False,
                "events_checked": index,
                "failed_event_id": event.id,
            }
        previous_hash = event.event_hash
    return {
        "valid": True,
        "events_checked": len(events),
        "head_hash": previous_hash,
    }


@app.get("/v1/license/status")
def license_status(_: Principal = Depends(current_principal)) -> dict:
    try:
        return license_agent().status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="License agent unavailable") from exc


@app.post("/v1/license/activate/online")
def license_activate_online(
    payload: LicenseActivate,
    _: Principal = Depends(require_owner),
) -> dict:
    try:
        return license_agent().activate_online(payload.activation_code)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Online activation failed") from exc


@app.post("/v1/license/offline/request")
def license_offline_request(
    payload: LicenseActivate,
    _: Principal = Depends(require_owner),
) -> dict:
    try:
        return license_agent().offline_request(payload.activation_code)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Offline request generation failed") from exc


@app.post("/v1/license/offline/apply")
def license_offline_apply(
    payload: OfflineApply,
    _: Principal = Depends(require_owner),
) -> dict:
    try:
        return license_agent().offline_apply(payload.activation_response)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Offline activation failed") from exc


@app.post("/v1/license/offline/release-code")
def license_offline_release_code(
    _: Principal = Depends(require_owner),
) -> dict[str, str]:
    try:
        return {"release_code": license_agent().offline_release_code()}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Offline release failed") from exc


@app.post("/v1/license/heartbeat")
def license_heartbeat(
    _: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    audit_head = db.scalar(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(1))
    try:
        return license_agent().heartbeat(
            protected_seat_count(db),
            audit_head.event_hash if audit_head else None,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Heartbeat failed") from exc


@app.post("/v1/license/billing")
def license_billing(_: Principal = Depends(require_admin)) -> dict[str, str]:
    try:
        return {"url": license_agent().billing_portal()}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Billing portal unavailable") from exc


@app.post("/v1/license/release")
def license_release(_: Principal = Depends(require_owner)) -> dict:
    try:
        return license_agent().release()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="License release failed") from exc


@app.get("/v1/stats")
def stats(
    _: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    users = list(db.scalars(select(MfaUser)))
    return {
        "company_name": settings.company_name,
        "protected_rdp_users": protected_seat_count(db),
        "total_users": len(users),
        "active_users": sum(user.status == UserStatus.active for user in users),
        "pending_users": sum(user.status == UserStatus.pending for user in users),
        "disabled_users": sum(user.status == UserStatus.disabled for user in users),
        "locked_users": sum(user.status == UserStatus.locked for user in users),
    }
