"""Customer data is central commercial data, separate from appliance identities."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import new_id, utcnow


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("cus"))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    company_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerToken(Base):
    __tablename__ = "customer_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Purchase(Base):
    __tablename__ = "customer_purchases"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: new_id("buy"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    seats: Mapped[int] = mapped_column(Integer)
    price_id: Mapped[str] = mapped_column(String(255))
    session_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerLicense(Base):
    __tablename__ = "customer_licenses"
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), primary_key=True)
    license_id: Mapped[str] = mapped_column(ForeignKey("licenses.id"), unique=True)
    subscription_id: Mapped[str] = mapped_column(String(255), unique=True)


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
