import hmac

from fastapi import Header, HTTPException, status

from .config import get_settings


def require_admin(x_bliss_license_admin: str | None = Header(default=None)) -> None:
    configured = get_settings().admin_api_key
    if not configured:
        raise HTTPException(status_code=503, detail="Admin authentication is not configured")
    if not x_bliss_license_admin or not hmac.compare_digest(x_bliss_license_admin, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
