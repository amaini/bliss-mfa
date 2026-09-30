import hmac

from fastapi import Header, HTTPException, status

from .config import get_settings


def require_bootstrap_admin(
    x_bliss_admin_key: str | None = Header(default=None),
) -> str:
    """Temporary bootstrap guard for Phase 0/1 management endpoints.

    Production customer authentication will replace this dependency. No
    management endpoint becomes usable unless BLISS_BOOTSTRAP_API_KEY is
    explicitly configured.
    """
    settings = get_settings()
    configured = settings.bliss_bootstrap_api_key
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Management authentication is not configured",
        )
    if not x_bliss_admin_key or not hmac.compare_digest(x_bliss_admin_key, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return "bootstrap-admin"
