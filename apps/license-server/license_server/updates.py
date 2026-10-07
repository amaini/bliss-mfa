"""Administrator-approved Windows releases, delivered to registered installations."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, Integer, String, Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .config import get_settings
from .crypto import b64url, canonical_json
from .db import Base, get_db
from .models import License
from .security import require_admin

router = APIRouter()


class WindowsRelease(Base):
    __tablename__ = "windows_releases"
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(40), unique=True)
    channel: Mapped[str] = mapped_column(String(20), default="stable")
    descriptor: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rollout_percent: Mapped[int] = mapped_column(Integer, default=0)


class PublishRelease(BaseModel):
    sequence: int = Field(ge=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    channel: str = Field(default="stable", pattern=r"^(stable|preview)$")
    archive_url: str = Field(max_length=2048)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size: int = Field(ge=1, le=2_000_000_000)
    provider_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    notes: str = Field(default="", max_length=2000)

    @field_validator("archive_url")
    @classmethod
    def https_only(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.fragment
        ):
            raise ValueError("Release downloads require HTTPS without embedded credentials")
        return value


class Rollout(BaseModel):
    enabled: bool
    rollout_percent: int = Field(ge=0, le=100)


class UpdateQuery(BaseModel):
    installation_id: str = Field(min_length=1, max_length=80)
    nonce: str = Field(min_length=20, max_length=200)
    channel: str = Field(default="stable", pattern=r"^(stable|preview)$")
    current_sequence: int = Field(ge=0)
    signature: str = Field(min_length=20, max_length=200)


def sign_release(descriptor: dict) -> dict[str, str]:
    filename = get_settings().update_signing_private_key_file
    if not filename:
        raise HTTPException(503, "Update signing key is not configured")
    key = serialization.load_pem_private_key(Path(filename).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise HTTPException(503, "Update signing key must be Ed25519")
    body = canonical_json(descriptor)
    return {"payload": b64url(body), "signature": b64url(key.sign(body))}


@router.post("/v1/admin/updates/releases", dependencies=[Depends(require_admin)], status_code=201)
def publish_release(payload: PublishRelease, db: Session = Depends(get_db)) -> dict:
    # Verify signing is configured before accepting a release into the catalog.
    sign_release(payload.model_dump())
    if db.scalar(select(WindowsRelease.sequence).order_by(WindowsRelease.sequence.desc()).limit(1)):
        maximum = db.scalar(
            select(WindowsRelease.sequence).order_by(WindowsRelease.sequence.desc()).limit(1)
        )
        if payload.sequence <= maximum:
            raise HTTPException(409, "Release sequence must increase")
    release = WindowsRelease(
        sequence=payload.sequence,
        version=payload.version,
        channel=payload.channel,
        descriptor=json.dumps(payload.model_dump()),
        enabled=False,
        rollout_percent=0,
    )
    db.add(release)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Release version or sequence already exists") from None
    return {"sequence": release.sequence, "enabled": False, "rollout_percent": 0}


@router.get("/v1/admin/updates/releases", dependencies=[Depends(require_admin)])
def releases(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {**json.loads(r.descriptor), "enabled": r.enabled, "rollout_percent": r.rollout_percent}
        for r in db.scalars(select(WindowsRelease).order_by(WindowsRelease.sequence.desc()))
    ]


@router.put("/v1/admin/updates/releases/{sequence}/rollout", dependencies=[Depends(require_admin)])
def set_rollout(sequence: int, payload: Rollout, db: Session = Depends(get_db)) -> dict:
    release = db.get(WindowsRelease, sequence)
    if not release:
        raise HTTPException(404, "Release not found")
    release.enabled = payload.enabled
    release.rollout_percent = payload.rollout_percent
    db.commit()
    return payload.model_dump()


@router.post("/v1/updates/check")
def check_update(payload: UpdateQuery, db: Session = Depends(get_db)) -> dict:
    # Reuse the device-signature and one-use challenge already used for licensing.
    from .main import get_active_challenge, verify_installation_signature

    license = db.scalar(select(License).where(License.installation_id == payload.installation_id))
    if not license:
        raise HTTPException(401, "Installation is not registered")
    challenge = get_active_challenge(db, payload.installation_id, payload.nonce)
    verify_installation_signature(
        license,
        payload.signature,
        {"action": "update-check", **payload.model_dump(exclude={"signature"})},
    )
    challenge.used_at = datetime.now(UTC)
    db.commit()
    # Security/repair updates remain available independent of payment status.
    bucket = (
        int.from_bytes(hashlib.sha256(payload.installation_id.encode()).digest()[:4], "big") % 100
    )
    for release in db.scalars(
        select(WindowsRelease)
        .where(
            WindowsRelease.enabled.is_(True),
            WindowsRelease.channel == payload.channel,
            WindowsRelease.sequence > payload.current_sequence,
        )
        .order_by(WindowsRelease.sequence.desc())
    ):
        if bucket < release.rollout_percent:
            now = datetime.now(UTC)
            descriptor = {
                **json.loads(release.descriptor),
                "schema": 1,
                "product": "bliss-mfa-windows",
                "issued_at": now.isoformat(),
                "expires_at": (now + timedelta(hours=1)).isoformat(),
            }
            return {"update": sign_release(descriptor)}
    return {"update": None}
