from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from httpx import HTTPError

from .client import LicenseServerClient
from .schemas import (
    BillingLinkResponse,
    HeartbeatInput,
    OfflineRequestCreate,
    OfflineResponseApply,
    OnlineActivationRequest,
    SeatAuthorizationRequest,
    SeatAuthorizationResponse,
)
from .security import require_local_auth
from .state import LicenseState


app = FastAPI(
    title="Bliss Secure MFA License Agent",
    version="0.1.0",
    dependencies=[Depends(require_local_auth)],
)
state = LicenseState()
client = LicenseServerClient(state)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/status")
def status() -> dict:
    return state.effective_status()


@app.post("/v1/activate/online")
def activate_online(payload: OnlineActivationRequest) -> dict:
    try:
        return client.activate_online(payload.activation_code)
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail="License server activation failed") from exc


@app.post("/v1/heartbeat")
def heartbeat(payload: HeartbeatInput) -> dict:
    try:
        return client.heartbeat(payload.protected_rdp_users, payload.audit_head_hash)
    except HTTPError as exc:
        # A failed heartbeat does not erase the last valid signed lease. The
        # effective status endpoint will move through offline_grace/restricted.
        current = state.effective_status()
        return {"heartbeat": "unreachable", "license": current}


@app.post("/v1/offline/request")
def offline_request(payload: OfflineRequestCreate) -> dict[str, str]:
    return {
        "installation_code": client.offline_installation_code(payload.activation_code),
    }


@app.post("/v1/offline/apply")
def offline_apply(payload: OfflineResponseApply) -> dict:
    try:
        return client.apply_offline_response(payload.activation_response)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/authorize/rdp-seat", response_model=SeatAuthorizationResponse)
def authorize_rdp_seat(payload: SeatAuthorizationRequest) -> SeatAuthorizationResponse:
    license = state.effective_status()
    maximum = int(license.get("max_rdp_users") or 0)
    requested = payload.current_protected_rdp_users + payload.delta
    license_state = str(license.get("state", "unlicensed"))

    allowed_state = license_state in {"active", "offline_grace"}
    allowed = allowed_state and requested <= maximum
    reason = None
    if not allowed_state:
        reason = f"License state {license_state} does not allow new protected users"
    elif requested > maximum:
        reason = f"RDP seat limit reached ({payload.current_protected_rdp_users}/{maximum})"

    return SeatAuthorizationResponse(
        allowed=allowed,
        current_protected_rdp_users=payload.current_protected_rdp_users,
        requested_total=requested,
        max_rdp_users=maximum,
        license_state=license_state,
        reason=reason,
    )


@app.post("/v1/billing/portal", response_model=BillingLinkResponse)
def billing_portal() -> BillingLinkResponse:
    try:
        return BillingLinkResponse(url=client.billing_portal())
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail="Billing portal is unavailable") from exc


@app.post("/v1/release")
def release() -> dict:
    try:
        return client.release()
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail="License release failed") from exc


@app.post("/v1/offline/release-code")
def offline_release_code() -> dict[str, str]:
    try:
        return {"release_code": state.create_offline_release_code()}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
