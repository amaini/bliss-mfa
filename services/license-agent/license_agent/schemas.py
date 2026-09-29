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

class BillingLinkResponse(BaseModel):
    url: str
