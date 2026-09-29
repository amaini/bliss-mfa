from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..db import get_db
from ..dependencies import get_multiotp_adapter
from ..models import MfaUser, Organization, UserStatus
from ..multiotp import MultiOtpAdapter
from ..schemas import (
    MfaUserCreate,
    MfaUserRead,
    UserActionRead,
    UserActionReason,
    UserResyncRequest,
)
from ..authorization import OrganizationAccess, require_org_manage, require_org_read


router = APIRouter(
    prefix="/organizations/{organization_id}/users",
    tags=["users"],
)


def get_organization_or_404(db: Session, organization_id: str) -> Organization:
    organization = db.get(Organization, organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


@router.get(
    "",
    response_model=list[MfaUserRead],
    dependencies=[Depends(require_org_read)],
)
def list_users(organization_id: str, db: Session = Depends(get_db)) -> list[MfaUser]:
    get_organization_or_404(db, organization_id)
    statement = (
        select(MfaUser)
        .where(MfaUser.organization_id == organization_id)
        .order_by(MfaUser.username)
    )
    return list(db.scalars(statement))


@router.post(
    "",
    response_model=MfaUserRead,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    organization_id: str,
    payload: MfaUserCreate,
    request: Request,
    access: OrganizationAccess = Depends(require_org_manage),
    db: Session = Depends(get_db),
    adapter: MultiOtpAdapter = Depends(get_multiotp_adapter),
) -> MfaUser:
    organization = get_organization_or_404(db, organization_id)

    existing = db.scalar(
        select(MfaUser).where(
            MfaUser.organization_id == organization_id,
            MfaUser.username == payload.username,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    active_count = db.scalar(
        select(func.count())
        .select_from(MfaUser)
        .where(
            MfaUser.organization_id == organization_id,
            MfaUser.status != UserStatus.disabled,
        )
    )
    if int(active_count or 0) >= organization.seat_limit:
        raise HTTPException(status_code=409, detail="Organization seat limit reached")

    engine_username = f"{organization.slug}:{payload.username}"
    try:
        adapter.create_totp_user(engine_username, email=payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="MFA engine user already exists") from exc

    user = MfaUser(
        organization_id=organization_id,
        username=payload.username,
        display_name=payload.display_name,
        email=str(payload.email) if payload.email else None,
        status=UserStatus.pending,
        multiotp_username=engine_username,
    )
    db.add(user)
    db.flush()

    write_audit(
        db,
        organization_id=organization_id,
        actor_id=access.actor_id,
        action="mfa.user.created",
        subject_type="mfa_user",
        subject_id=user.id,
        source_ip=request.client.host if request.client else None,
    )

    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/unlock", response_model=UserActionRead)
def unlock_user(
    organization_id: str,
    user_id: str,
    payload: UserActionReason,
    request: Request,
    access: OrganizationAccess = Depends(require_org_manage),
    db: Session = Depends(get_db),
    adapter: MultiOtpAdapter = Depends(get_multiotp_adapter),
) -> UserActionRead:
    user = db.scalar(
        select(MfaUser).where(
            MfaUser.id == user_id,
            MfaUser.organization_id == organization_id,
        )
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    adapter.unlock_user(user.multiotp_username)
    if user.status == UserStatus.locked:
        user.status = UserStatus.active

    write_audit(
        db,
        organization_id=organization_id,
        actor_id=access.actor_id,
        action="mfa.user.unlocked",
        subject_type="mfa_user",
        subject_id=user.id,
        reason=payload.reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return UserActionRead(ok=True, status=user.status.value)


@router.post("/{user_id}/disable", response_model=UserActionRead)
def disable_user(
    organization_id: str,
    user_id: str,
    payload: UserActionReason,
    request: Request,
    access: OrganizationAccess = Depends(require_org_manage),
    db: Session = Depends(get_db),
    adapter: MultiOtpAdapter = Depends(get_multiotp_adapter),
) -> UserActionRead:
    user = db.scalar(
        select(MfaUser).where(
            MfaUser.id == user_id,
            MfaUser.organization_id == organization_id,
        )
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    adapter.disable_user(user.multiotp_username)
    user.status = UserStatus.disabled
    write_audit(
        db,
        organization_id=organization_id,
        actor_id=access.actor_id,
        action="mfa.user.disabled",
        subject_type="mfa_user",
        subject_id=user.id,
        reason=payload.reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return UserActionRead(ok=True, status=user.status.value)


@router.post("/{user_id}/enable", response_model=UserActionRead)
def enable_user(
    organization_id: str,
    user_id: str,
    payload: UserActionReason,
    request: Request,
    access: OrganizationAccess = Depends(require_org_manage),
    db: Session = Depends(get_db),
    adapter: MultiOtpAdapter = Depends(get_multiotp_adapter),
) -> UserActionRead:
    user = db.scalar(
        select(MfaUser).where(
            MfaUser.id == user_id,
            MfaUser.organization_id == organization_id,
        )
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    adapter.enable_user(user.multiotp_username)
    user.status = UserStatus.active
    write_audit(
        db,
        organization_id=organization_id,
        actor_id=access.actor_id,
        action="mfa.user.enabled",
        subject_type="mfa_user",
        subject_id=user.id,
        reason=payload.reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return UserActionRead(ok=True, status=user.status.value)


@router.post("/{user_id}/resync", response_model=UserActionRead)
def resync_user(
    organization_id: str,
    user_id: str,
    payload: UserResyncRequest,
    request: Request,
    access: OrganizationAccess = Depends(require_org_manage),
    db: Session = Depends(get_db),
    adapter: MultiOtpAdapter = Depends(get_multiotp_adapter),
) -> UserActionRead:
    user = db.scalar(
        select(MfaUser).where(
            MfaUser.id == user_id,
            MfaUser.organization_id == organization_id,
        )
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    ok = adapter.resync_user(user.multiotp_username, payload.otp1, payload.otp2)
    write_audit(
        db,
        organization_id=organization_id,
        actor_id=access.actor_id,
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
    return UserActionRead(ok=True, status=user.status.value)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    organization_id: str,
    user_id: str,
    reason: str,
    request: Request,
    access: OrganizationAccess = Depends(require_org_manage),
    db: Session = Depends(get_db),
    adapter: MultiOtpAdapter = Depends(get_multiotp_adapter),
) -> None:
    user = db.scalar(
        select(MfaUser).where(
            MfaUser.id == user_id,
            MfaUser.organization_id == organization_id,
        )
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if len(reason.strip()) < 3:
        raise HTTPException(status_code=422, detail="Deletion reason is required")

    adapter.delete_user(user.multiotp_username)
    user_id_for_audit = user.id
    db.delete(user)
    write_audit(
        db,
        organization_id=organization_id,
        actor_id=access.actor_id,
        action="mfa.user.deleted",
        subject_type="mfa_user",
        subject_id=user_id_for_audit,
        reason=reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
