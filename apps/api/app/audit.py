import uuid

from sqlalchemy.orm import Session

from .models import AuditEvent


def write_audit(
    db: Session,
    *,
    organization_id: str,
    actor_id: str | None,
    action: str,
    actor_type: str = "portal_admin",
    subject_type: str,
    subject_id: str | None,
    reason: str | None = None,
    success: bool = True,
    source_ip: str | None = None,
    correlation_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        reason=reason,
        success=success,
        source_ip=source_ip,
        correlation_id=correlation_id or str(uuid.uuid4()),
    )
    db.add(event)
    return event
