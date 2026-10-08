import subprocess

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from .config import get_settings
from .runner import AdapterInputError, MultiOtpCliRunner
from .schemas import CommandResponse, OtpVerify, ProvisioningResponse, ResyncRequest, UserCreate
from .security import require_internal_auth

app = FastAPI(title="Bliss multiOTP Adapter", version="0.1.0")
runner = MultiOtpCliRunner()


@app.exception_handler(AdapterInputError)
async def invalid_input(request, exc):
    return JSONResponse(status_code=422, content={"detail": "Invalid engine input"})


@app.exception_handler(subprocess.TimeoutExpired)
async def engine_timeout(request, exc):
    # Never serialize exc: subprocess arguments can contain a submitted OTP.
    return JSONResponse(status_code=504, content={"detail": "MFA engine timed out"})


@app.exception_handler(OSError)
async def engine_unavailable(request, exc):
    return JSONResponse(status_code=503, content={"detail": "MFA engine unavailable"})


def require_writes_enabled() -> None:
    if not get_settings().adapter_enable_writes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Adapter writes are disabled",
        )


SUCCESS_CODES = {
    "create": {11}, "list": {19}, "provisioning": {17}, "verify": {0},
    "lock": {11}, "unlock": {11}, "disable": {11}, "enable": {11}, "resync": {14},
    "revoke": {19}, "delete": {12, 21}, "without2fa": {11},
}
WITHOUT2FA, NOT_WITHOUT2FA = 8, 7  # -iswithout2fa results; anything else means no such user


def command_response(operation: str, returncode: int, *, authentication_disabled: bool = False) -> CommandResponse:
    # Missing-user deletion is idempotent: the required postcondition is absence.
    return CommandResponse(
        ok=returncode in SUCCESS_CODES[operation], returncode=returncode,
        authentication_disabled=authentication_disabled,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/users", dependencies=[Depends(require_internal_auth)])
def list_users() -> dict[str, list[str]]:
    result = runner.users_list()
    if result.returncode not in SUCCESS_CODES["list"]:
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
        # Enrolling an account that signs in password-only replaces its without2FA record.
        if runner.is_without2fa(payload.username).returncode == WITHOUT2FA:
            removed = runner.delete_user(payload.username)
            if removed.returncode not in SUCCESS_CODES["delete"]:
                return command_response("delete", removed.returncode)
        result = runner.create_totp_user(payload.username)
    except AdapterInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return command_response("create", result.returncode)


@app.post(
    "/v1/users/{username}/without2fa",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def create_without2fa(username: str) -> CommandResponse:
    kind = runner.is_without2fa(username).returncode
    if kind == WITHOUT2FA:
        return CommandResponse(ok=True, returncode=kind, authentication_disabled=False)
    if kind == NOT_WITHOUT2FA:  # an enrolled TOTP user is never downgraded here
        return CommandResponse(ok=False, returncode=kind, authentication_disabled=False)
    return command_response("without2fa", runner.create_without2fa_user(username).returncode)


@app.get("/v1/users/{username}/without2fa", dependencies=[Depends(require_internal_auth)])
def without2fa_status(username: str) -> dict[str, bool]:
    kind = runner.is_without2fa(username).returncode
    return {"without2fa": kind == WITHOUT2FA, "exists": kind in {WITHOUT2FA, NOT_WITHOUT2FA}}


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
    if result.returncode not in SUCCESS_CODES["provisioning"]:
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
    return command_response("verify", result.returncode)


@app.post(
    "/v1/users/{username}/unlock",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def unlock(username: str) -> CommandResponse:
    return command_response("unlock", runner.unlock(username).returncode)


@app.post(
    "/v1/users/{username}/lock",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def lock(username: str) -> CommandResponse:
    return command_response("lock", runner.lock(username).returncode)


@app.post(
    "/v1/users/{username}/disable",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def disable(username: str) -> CommandResponse:
    return command_response("disable", runner.disable(username).returncode)


@app.post(
    "/v1/users/{username}/enable",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def enable(username: str) -> CommandResponse:
    return command_response("enable", runner.enable(username).returncode)


@app.post(
    "/v1/users/{username}/resync",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def resync(username: str, payload: ResyncRequest) -> CommandResponse:
    result = runner.resync(username, payload.otp1, payload.otp2)
    return command_response("resync", result.returncode)


@app.post(
    "/v1/users/{username}/revoke",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def revoke(username: str) -> CommandResponse:
    result = runner.revoke_token(username)
    return command_response(
        "revoke", result.returncode, authentication_disabled=result.authentication_disabled,
    )


@app.delete(
    "/v1/users/{username}",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def delete_user(username: str) -> CommandResponse:
    return command_response("delete", runner.delete_user(username).returncode)
