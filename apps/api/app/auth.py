from __future__ import annotations

import hmac
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient

from .config import get_settings


@dataclass(frozen=True)
class Principal:
    subject: str
    email: str | None
    groups: frozenset[str]
    bootstrap: bool = False

    @property
    def actor_id(self) -> str:
        return self.subject


_jwks_clients: dict[str, PyJWKClient] = {}


def _get_jwks_client(url: str) -> PyJWKClient:
    client = _jwks_clients.get(url)
    if client is None:
        client = PyJWKClient(url)
        _jwks_clients[url] = client
    return client


def _bootstrap_principal(x_bliss_admin_key: str | None) -> Principal | None:
    settings = get_settings()
    if settings.app_env == "production":
        return None

    configured = settings.bliss_bootstrap_api_key
    if not configured or not x_bliss_admin_key:
        return None

    if not hmac.compare_digest(x_bliss_admin_key, configured):
        return None

    return Principal(
        subject="bootstrap-admin",
        email=None,
        groups=frozenset({settings.oidc_staff_admin_group}),
        bootstrap=True,
    )


def get_principal(
    authorization: str | None = Header(default=None),
    x_bliss_admin_key: str | None = Header(default=None),
) -> Principal:
    bootstrap = _bootstrap_principal(x_bliss_admin_key)
    if bootstrap:
        return bootstrap

    settings = get_settings()
    if not settings.oidc_issuer or not settings.oidc_audience or not settings.oidc_jwks_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC authentication is not configured",
        )

    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    token = authorization[len(prefix) :].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    try:
        signing_key = _get_jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={
                "require": ["exp", "iat", "sub"],
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    groups_claim = claims.get(settings.oidc_groups_claim, [])
    if isinstance(groups_claim, str):
        groups = frozenset({groups_claim})
    else:
        groups = frozenset(str(group) for group in groups_claim or [])

    return Principal(
        subject=str(claims["sub"]),
        email=str(claims["email"]) if claims.get("email") else None,
        groups=groups,
    )


def require_staff_principal(
    principal: Principal = Depends(get_principal),
) -> Principal:

    settings = get_settings()
    allowed = {
        settings.oidc_staff_admin_group,
        settings.oidc_staff_technician_group,
        settings.oidc_staff_billing_group,
    }
    if not principal.groups.intersection(allowed):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required")
    return principal


def require_admin_principal(
    principal: Principal = Depends(get_principal),
) -> Principal:

    settings = get_settings()
    if settings.oidc_staff_admin_group not in principal.groups:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return principal
