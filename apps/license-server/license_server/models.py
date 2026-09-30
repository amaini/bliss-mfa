from __future__ import annotations

import enum
import secrets
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12)}"


class LicenseType(str, enum.Enum):
    online = "online"
    offline = "offline"


class LicenseStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"
    revoked = "revoked"
    expired = "expired"


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("lic"))
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(320))
    license_type: Mapped[LicenseType] = mapped_column(Enum(LicenseType), nullable=False)
    status: Mapped[LicenseStatus] = mapped_column(
        Enum(LicenseStatus), default=LicenseStatus.active, nullable=False
    )
    max_rdp_users: Mapped[int] = mapped_column(Integer, nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255))
    activation_code_hash: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    installation_id: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    installation_public_key: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reported_seats: Mapped[int | None] = mapped_column(Integer)
    last_software_version: Mapped[str | None] = mapped_column(String(100))
    last_machine_fingerprint: Mapped[str | None] = mapped_column(String(128))
    last_audit_head_hash: Mapped[str | None] = mapped_column(String(128))
    offline_validity_days: Mapped[int | None] = mapped_column(Integer)
    offline_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Challenge(Base):
    __tablename__ = "license_challenges"

    nonce_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    installation_id: Mapped[str] = mapped_column(String(80), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivationEvent(Base):
    __tablename__ = "license_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("evt"))
    license_id: Mapped[str] = mapped_column(String(80), index=True)
    installation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
