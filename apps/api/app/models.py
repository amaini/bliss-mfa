from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class OrganizationStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"
    closed = "closed"


class UserStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    disabled = "disabled"
    locked = "locked"


class DeviceStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    revoked = "revoked"
    replaced = "replaced"


class EnrollmentStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    expired = "expired"
    cancelled = "cancelled"
    failed = "failed"


class SubscriptionStatus(str, enum.Enum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    ended = "ended"


class SignupStatus(str, enum.Enum):
    checkout_created = "checkout_created"
    paid_pending_setup = "paid_pending_setup"
    completed = "completed"
    canceled = "canceled"


class PortalUserStatus(str, enum.Enum):
    invited = "invited"
    active = "active"
    disabled = "disabled"


class MembershipRole(str, enum.Enum):
    customer_admin = "customer_admin"
    customer_operator = "customer_operator"
    readonly = "readonly"


class StaffRole(str, enum.Enum):
    super_admin = "super_admin"
    technician = "technician"
    billing = "billing"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    status: Mapped[OrganizationStatus] = mapped_column(
        Enum(OrganizationStatus), default=OrganizationStatus.active, nullable=False
    )
    seat_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list[MfaUser]] = relationship(back_populates="organization")
    subscription: Mapped[Subscription | None] = relationship(
        back_populates="organization", uselist=False
    )


class MfaUser(Base):
    __tablename__ = "mfa_users"
    __table_args__ = (UniqueConstraint("organization_id", "username", name="uq_org_username"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.pending)
    multiotp_username: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    organization: Mapped[Organization] = relationship(back_populates="users")
    devices: Mapped[list[MfaDevice]] = relationship(back_populates="user")
    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="user")


class MfaDevice(Base):
    __tablename__ = "mfa_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("mfa_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(120), default="Authenticator")
    status: Mapped[DeviceStatus] = mapped_column(Enum(DeviceStatus), default=DeviceStatus.pending)
    engine_reference: Mapped[str | None] = mapped_column(String(255))
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[MfaUser] = relationship(back_populates="devices")


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("mfa_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str | None] = mapped_column(
        ForeignKey("mfa_devices.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    status: Mapped[EnrollmentStatus] = mapped_column(
        Enum(EnrollmentStatus), default=EnrollmentStatus.pending
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[MfaUser] = relationship(back_populates="enrollments")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    source_ip: Mapped[str | None] = mapped_column(String(64))
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_price_id: Mapped[str | None] = mapped_column(String(255))
    plan_code: Mapped[str] = mapped_column(String(80), default="starter")
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.trialing
    )
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    organization: Mapped[Organization] = relationship(back_populates="subscription")


class PendingSignup(Base):
    __tablename__ = "pending_signups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    plan_code: Mapped[str] = mapped_column(String(80), nullable=False)
    onboarding_token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[SignupStatus] = mapped_column(
        Enum(SignupStatus), default=SignupStatus.checkout_created, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class StripeWebhookEvent(Base):
    __tablename__ = "stripe_webhook_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PortalUser(Base):
    __tablename__ = "portal_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[PortalUserStatus] = mapped_column(
        Enum(PortalUserStatus), default=PortalUserStatus.invited, nullable=False
    )
    is_bliss_staff: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    staff_role: Mapped[StaffRole | None] = mapped_column(Enum(StaffRole))
    external_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "portal_user_id", name="uq_org_portal_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    portal_user_id: Mapped[str] = mapped_column(
        ForeignKey("portal_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole), default=MembershipRole.readonly, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
