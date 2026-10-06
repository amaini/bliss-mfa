from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..authorization import require_org_read
from ..db import get_db
from ..models import (
    DeviceStatus,
    Enrollment,
    EnrollmentStatus,
    MfaDevice,
    MfaUser,
    Organization,
    UserStatus,
)
from ..schemas import OrganizationStatsRead

router = APIRouter(
    prefix="/organizations/{organization_id}/stats",
    tags=["dashboard"],
    dependencies=[Depends(require_org_read)],
)


@router.get("", response_model=OrganizationStatsRead)
def organization_stats(
    organization_id: str,
    db: Session = Depends(get_db),
) -> OrganizationStatsRead:
    organization = db.get(Organization, organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    def user_count(status: UserStatus | None = None) -> int:
        statement = select(func.count()).select_from(MfaUser).where(
            MfaUser.organization_id == organization_id
        )
        if status is not None:
            statement = statement.where(MfaUser.status == status)
        return int(db.scalar(statement) or 0)

    active_devices = int(
        db.scalar(
            select(func.count())
            .select_from(MfaDevice)
            .join(MfaUser, MfaDevice.user_id == MfaUser.id)
            .where(
                MfaUser.organization_id == organization_id,
                MfaDevice.status == DeviceStatus.active,
            )
        )
        or 0
    )

    pending_enrollments = int(
        db.scalar(
            select(func.count())
            .select_from(Enrollment)
            .join(MfaUser, Enrollment.user_id == MfaUser.id)
            .where(
                MfaUser.organization_id == organization_id,
                Enrollment.status == EnrollmentStatus.pending,
            )
        )
        or 0
    )

    return OrganizationStatsRead(
        organization_id=organization_id,
        total_users=user_count(),
        active_users=user_count(UserStatus.active),
        pending_users=user_count(UserStatus.pending),
        disabled_users=user_count(UserStatus.disabled),
        locked_users=user_count(UserStatus.locked),
        active_devices=active_devices,
        pending_enrollments=pending_enrollments,
        seat_limit=organization.seat_limit,
    )
