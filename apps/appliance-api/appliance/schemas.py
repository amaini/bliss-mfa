from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BootstrapRequest(BaseModel):
    setup_token: str
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    display_name: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    display_name: str | None = Field(default=None, max_length=200)
    role: str = Field(pattern=r"^(owner|admin|operator|readonly)$")


class AdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    display_name: str | None
    role: str
    disabled: bool
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.@-]{1,100}$")
    display_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    display_name: str | None
    email: str | None
    status: str
    protected_rdp: bool
    created_at: datetime


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class ResyncRequest(ReasonRequest):
    otp1: str = Field(pattern=r"^\d{4,16}$")
    otp2: str = Field(pattern=r"^\d{4,16}$")


class VerifyRequest(BaseModel):
    otp: str = Field(pattern=r"^\d{4,16}$")


class EnrollmentRead(BaseModel):
    provisioning_uri: str


class LicenseActivate(BaseModel):
    activation_code: str


class OfflineApply(BaseModel):
    activation_response: str


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    actor_id: str | None
    action: str
    subject_type: str
    subject_id: str | None
    reason: str | None
    success: bool
    source_ip: str | None
    previous_hash: str | None
    event_hash: str
    created_at: datetime
