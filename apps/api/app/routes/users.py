from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..db import get_db
from ..dependencies import get_multiotp_adapter
from ..models import MfaUser, Organization, UserStatus
from ..multiotp import MultiOtpAdapter
from ..schemas import MfaUserCreate, MfaUserRead
from ..security import require_bootstrap_admin


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
    dependencies=[Depends(require_bootstrap_admin)],
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
    actor_id: str = Depends(require_bootstrap_admin),
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
        actor_id=actor_id,
        action="mfa.user.created",
        subject_type="mfa_user",
        subject_id=user.id,
        source_ip=request.client.host if request.client else None,
    )

    db.commit()
    db.refresh(user)
    return user
