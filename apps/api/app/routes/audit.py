from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..authorization import require_org_read
from ..db import get_db
from ..models import AuditEvent, Organization
from ..schemas import AuditEventRead

router = APIRouter(
    prefix="/organizations/{organization_id}/audit",
    tags=["audit"],
    dependencies=[Depends(require_org_read)],
)


@router.get("", response_model=list[AuditEventRead])
def list_audit_events(
    organization_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AuditEvent]:
    if not db.get(Organization, organization_id):
        raise HTTPException(status_code=404, detail="Organization not found")

    statement = (
        select(AuditEvent)
        .where(AuditEvent.organization_id == organization_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(statement))
