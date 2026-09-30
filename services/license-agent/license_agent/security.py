import hmac

from fastapi import Header, HTTPException

from .config import get_settings


def require_local_auth(authorization: str | None = Header(default=None)) -> None:
    configured = get_settings().agent_shared_token
    if not configured:
        raise HTTPException(status_code=503, detail="License agent authentication is not configured")
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not hmac.compare_digest(authorization[len(prefix):], configured):
        raise HTTPException(status_code=401, detail="Unauthorized")
