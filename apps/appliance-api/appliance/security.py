from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AdminRole, LocalAdmin


hasher = PasswordHasher()


@dataclass(frozen=True)
class Principal:
    id: str
    email: str
    role: AdminRole


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def issue_token(admin: LocalAdmin) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": admin.id,
            "email": admin.email,
            "role": admin.role.value,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=settings.jwt_minutes)).timestamp()),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def current_principal(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(
            authorization[7:].strip(),
            get_settings().jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc

    admin = db.get(LocalAdmin, str(payload.get("sub", "")))
    if not admin or admin.disabled:
        raise HTTPException(status_code=401, detail="Account unavailable")
    return Principal(id=admin.id, email=admin.email, role=admin.role)


def require_operator(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.role not in {AdminRole.owner, AdminRole.admin, AdminRole.operator}:
        raise HTTPException(status_code=403, detail="Operator access required")
    return principal


def require_admin(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.role not in {AdminRole.owner, AdminRole.admin}:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return principal


def require_owner(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.role != AdminRole.owner:
        raise HTTPException(status_code=403, detail="Owner access required")
    return principal
