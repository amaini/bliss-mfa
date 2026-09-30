import hmac

from fastapi import Header, HTTPException, status

from .config import get_settings


def require_internal_auth(authorization: str | None = Header(default=None)) -> None:
    configured = get_settings().adapter_shared_token
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Adapter authentication is not configured",
        )

    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    supplied = authorization[len(prefix):]
    if not hmac.compare_digest(supplied, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
