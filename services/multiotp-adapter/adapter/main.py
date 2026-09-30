from fastapi import Depends, FastAPI, HTTPException, status

from .config import get_settings
from .runner import AdapterInputError, MultiOtpCliRunner
from .schemas import CommandResponse, OtpVerify, ProvisioningResponse, ResyncRequest, UserCreate
from .security import require_internal_auth


app = FastAPI(title="Bliss multiOTP Adapter", version="0.1.0")
runner = MultiOtpCliRunner()


def require_writes_enabled() -> None:
    if not get_settings().adapter_enable_writes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Adapter writes are disabled",
        )


def command_response(returncode: int) -> CommandResponse:
    return CommandResponse(ok=returncode == 0, returncode=returncode)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/users", dependencies=[Depends(require_internal_auth)])
def list_users() -> dict[str, list[str]]:
    result = runner.users_list()
    if result.returncode != 0:
        raise HTTPException(status_code=502, detail="multiOTP users list failed")
    users = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {"users": users}


@app.post(
    "/v1/users",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def create_user(payload: UserCreate) -> CommandResponse:
    try:
        result = runner.create_totp_user(payload.username)
    except AdapterInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return command_response(result.returncode)


@app.get(
    "/v1/users/{username}/provisioning",
    response_model=ProvisioningResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def provisioning(username: str) -> ProvisioningResponse:
    try:
        result = runner.provisioning_url(username)
    except AdapterInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result.returncode != 0:
        raise HTTPException(status_code=502, detail="multiOTP provisioning failed")

    uri = result.stdout.strip()
    if not uri.startswith("otpauth://"):
        raise HTTPException(status_code=502, detail="Unexpected provisioning response")
    return ProvisioningResponse(provisioning_uri=uri)


@app.post(
    "/v1/users/{username}/verify",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth)],
)
def verify(username: str, payload: OtpVerify) -> CommandResponse:
    try:
        result = runner.verify(username, payload.otp)
    except AdapterInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return command_response(result.returncode)


@app.post(
    "/v1/users/{username}/unlock",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def unlock(username: str) -> CommandResponse:
    return command_response(runner.unlock(username).returncode)


@app.post(
    "/v1/users/{username}/disable",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def disable(username: str) -> CommandResponse:
    return command_response(runner.disable(username).returncode)


@app.post(
    "/v1/users/{username}/enable",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def enable(username: str) -> CommandResponse:
    return command_response(runner.enable(username).returncode)


@app.post(
    "/v1/users/{username}/resync",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def resync(username: str, payload: ResyncRequest) -> CommandResponse:
    result = runner.resync(username, payload.otp1, payload.otp2)
    return command_response(result.returncode)


@app.post(
    "/v1/users/{username}/revoke",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def revoke(username: str) -> CommandResponse:
    return command_response(runner.revoke_token(username).returncode)


@app.delete(
    "/v1/users/{username}",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def delete_user(username: str) -> CommandResponse:
    return command_response(runner.delete_user(username).returncode)
