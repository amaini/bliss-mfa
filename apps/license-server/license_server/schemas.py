from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LicenseCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=200)
    customer_email: EmailStr | None = None
    license_type: str = Field(pattern=r"^(online|offline)$")
    max_rdp_users: int = Field(ge=1, le=100000)
    offline_days: int | None = Field(default=None, ge=1, le=3650)


class LicenseCreated(BaseModel):
    license_id: str
    activation_code: str
    license_type: str
    max_rdp_users: int


class ActivateOnlineRequest(BaseModel):
    activation_code: str = Field(min_length=12, max_length=200)
    installation_id: str = Field(min_length=8, max_length=80)
    installation_public_key: str = Field(min_length=32, max_length=5000)


class LeaseResponse(BaseModel):
    signed_lease: str
    state: str
    max_rdp_users: int
    lease_expires_at: datetime
    grace_expires_at: datetime | None = None


class ChallengeRequest(BaseModel):
    installation_id: str = Field(min_length=8, max_length=80)


class ChallengeResponse(BaseModel):
    nonce: str
    expires_at: datetime


class HeartbeatRequest(BaseModel):
    installation_id: str
    nonce: str
    signature: str
    protected_rdp_users: int = Field(ge=0, le=1000000)
    software_version: str = Field(default="unknown", max_length=100)
    machine_fingerprint: str | None = Field(default=None, max_length=128)
    audit_head_hash: str | None = Field(default=None, max_length=128)


class ReleaseRequest(BaseModel):
    installation_id: str
    nonce: str
    signature: str


class OfflineIssueRequest(BaseModel):
    installation_code: str = Field(min_length=20, max_length=10000)
    max_rdp_users: int | None = Field(default=None, ge=1, le=100000)
    validity_days: int | None = Field(default=None, ge=1, le=3650)


class BillingPortalRequest(BaseModel):
    installation_id: str


class BillingPortalResponse(BaseModel):
    url: str


class LicenseStatusRead(BaseModel):
    id: str
    customer_name: str
    license_type: str
    status: str
    max_rdp_users: int
    installation_id: str | None
    last_seen_at: datetime | None
    last_reported_seats: int | None
    offline_expires_at: datetime | None


class OfflineReleaseCode(BaseModel):
    release_code: str = Field(min_length=20, max_length=10000)


class StripeLinkRequest(BaseModel):
    customer_id: str = Field(min_length=3, max_length=255)
    subscription_id: str | None = Field(default=None, max_length=255)
