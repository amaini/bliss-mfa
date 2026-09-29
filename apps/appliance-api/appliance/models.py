from __future__ import annotations

import enum
import hashlib
import json
import secrets
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(10)}"


class AdminRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    operator = "operator"
    readonly = "readonly"


class UserStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    disabled = "disabled"
    locked = "locked"
    revoked = "revoked"


class LocalAdmin(Base):
    __tablename__ = "local_admins"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("adm"))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[AdminRole] = mapped_column(Enum(AdminRole), default=AdminRole.readonly)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MfaUser(Base):
    __tablename__ = "mfa_users"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("usr"))
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.pending)
    protected_rdp: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    engine_username: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("evt"))
    actor_id: Mapped[str | None] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    subject_type: Mapped[str] = mapped_column(String(80))
    subject_id: Mapped[str | None] = mapped_column(String(80))
    reason: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    source_ip: Mapped[str | None] = mapped_column(String(64))
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def event_digest(
    *,
    actor_id: str | None,
    action: str,
    subject_type: str,
    subject_id: str | None,
    reason: str | None,
    success: bool,
    previous_hash: str | None,
    created_at: datetime,
) -> str:
    normalized_created_at = created_at
    if normalized_created_at.tzinfo is None:
        normalized_created_at = normalized_created_at.replace(tzinfo=timezone.utc)
    normalized_created_at = normalized_created_at.astimezone(timezone.utc)

    payload = json.dumps(
        {
            "actor_id": actor_id,
            "action": action,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "reason": reason,
            "success": success,
            "previous_hash": previous_hash,
            "created_at": normalized_created_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()
