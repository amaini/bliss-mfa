from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")
    seat_limit: int = Field(default=10, ge=1, le=10000)


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    status: str
    seat_limit: int
    created_at: datetime


class MfaUserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None


class MfaUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    username: str
    display_name: str | None
    email: str | None
    status: str
    multiotp_username: str
    created_at: datetime


class EnrollmentStartRead(BaseModel):
    enrollment_token: str
    provisioning_uri: str
    expires_at: datetime


class EnrollmentVerifyRequest(BaseModel):
    enrollment_token: str = Field(min_length=32, max_length=512)
    otp: str = Field(pattern=r"^\d{6,10}$")


class EnrollmentVerifyRead(BaseModel):
    verified: bool
    user_id: str
    device_id: str


class RevokeDeviceRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class HealthRead(BaseModel):
    status: str
    service: str


class CheckoutCreateRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    plan_code: str = Field(pattern=r"^(starter|business|business_plus)$")


class CheckoutCreateRead(BaseModel):
    checkout_url: str
    checkout_session_id: str
