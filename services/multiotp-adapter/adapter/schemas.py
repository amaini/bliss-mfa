from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=255)


class OtpVerify(BaseModel):
    otp: str = Field(pattern=r"^[0-9]{4,16}$")


class ResyncRequest(BaseModel):
    otp1: str = Field(pattern=r"^[0-9]{4,16}$")
    otp2: str = Field(pattern=r"^[0-9]{4,16}$")


class CommandResponse(BaseModel):
    ok: bool
    returncode: int


class ProvisioningResponse(BaseModel):
    provisioning_uri: str
