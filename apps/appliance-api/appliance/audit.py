from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEvent, event_digest, utcnow


def write_audit(
    db: Session,
    *,
    actor_id: str | None,
    action: str,
    subject_type: str,
    subject_id: str | None,
    reason: str | None = None,
    success: bool = True,
    source_ip: str | None = None,
) -> AuditEvent:
    previous = db.scalar(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(1))
    previous_hash = previous.event_hash if previous else None
    created_at = utcnow()
    digest = event_digest(
        actor_id=actor_id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        reason=reason,
        success=success,
        previous_hash=previous_hash,
        created_at=created_at,
    )
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        reason=reason,
        success=success,
        source_ip=source_ip,
        previous_hash=previous_hash,
        event_hash=digest,
        created_at=created_at,
    )
    db.add(event)
    return event
