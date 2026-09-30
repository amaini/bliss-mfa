from pydantic import BaseModel, Field

class OnlineActivationRequest(BaseModel):
    activation_code: str = Field(min_length=12, max_length=200)

class OfflineRequestCreate(BaseModel):
    activation_code: str = Field(min_length=12, max_length=200)

class OfflineResponseApply(BaseModel):
    activation_response: str = Field(min_length=20, max_length=10000)

class SeatAuthorizationRequest(BaseModel):
    current_protected_rdp_users: int = Field(ge=0)
    delta: int = Field(default=1, ge=0, le=1000)

class SeatAuthorizationResponse(BaseModel):
    allowed: bool
    current_protected_rdp_users: int
    requested_total: int
    max_rdp_users: int
    license_state: str
    reason: str | None = None

class HeartbeatInput(BaseModel):
    protected_rdp_users: int = Field(ge=0)
    audit_head_hash: str | None = Field(default=None, max_length=128)

class BillingLinkResponse(BaseModel):
    url: str


class SeatIdentityRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.:@-]{1,255}$")

class SeatIdentityResponse(BaseModel):
    allowed: bool
    seat_count: int
    max_rdp_users: int
    already_reserved: bool = False
    reason: str | None = None
