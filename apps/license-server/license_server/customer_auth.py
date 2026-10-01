import hashlib
import secrets
import smtplib
from datetime import timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .config import get_settings
from .customer_models import Customer, CustomerToken
from .db import get_db
from .models import utcnow

COOKIE = "bliss_customer_session"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    hashed = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return salt.hex() + ":" + hashed.hex()


def password_matches(stored: str, password: str) -> bool:
    salt, expected = stored.split(":")
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return secrets.compare_digest(actual.hex(), expected)


def issue_token(db: Session, customer_id: str, purpose: str, minutes: int) -> str:
    token = secrets.token_urlsafe(32)
    db.add(CustomerToken(token_hash=digest(token), customer_id=customer_id,
                         purpose=purpose, expires_at=utcnow() + timedelta(minutes=minutes)))
    return token


def valid_token(db: Session, token: str, purpose: str) -> CustomerToken:
    row = db.get(CustomerToken, digest(token))
    if not row or row.purpose != purpose:
        raise HTTPException(401, "Invalid or expired token")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= utcnow():
        raise HTTPException(401, "Invalid or expired token")
    return row


def current_customer(request: Request, db: Session = Depends(get_db)) -> Customer:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Sign in to continue")
    row = valid_token(db, token, "session")
    customer = db.get(Customer, row.customer_id)
    if not customer:
        raise HTTPException(401, "Account unavailable")
    return customer


def invalidate_tokens(db: Session, customer_id: str, purpose: str) -> None:
    db.execute(delete(CustomerToken).where(CustomerToken.customer_id == customer_id,
                                          CustomerToken.purpose == purpose))


def send_account_mail(email: str, token: str, purpose: str) -> None:
    settings = get_settings()
    fragment = "verify" if purpose == "verify" else "reset"
    link = f"{settings.customer_portal_url.rstrip('/')}/customer#{fragment}={token}"
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = email
    message["Subject"] = "Verify your Bliss account" if purpose == "verify" else "Reset your Bliss password"
    message.set_content(f"Open this link to continue:\n{link}\n\nIf you did not request this, ignore it.")
    if settings.resend_api_key:
        try:
            response = httpx.post('https://api.resend.com/emails',
                headers={'Authorization': 'Bearer ' + settings.resend_api_key,
                         'Idempotency-Key': 'bliss-account-' + digest(token)},
                json={'from': settings.mail_from, 'to': [email],
                      'subject': str(message['Subject']), 'text': message.get_content()},
                timeout=15, trust_env=False)
            response.raise_for_status()
            if not isinstance(response.json().get('id'), str):
                raise ValueError('Missing email delivery identifier')
        except (httpx.HTTPError, ValueError, AttributeError):
            # Provider errors can contain customer email or private verification links.
            raise HTTPException(503, 'Email delivery is temporarily unavailable. Try again later.') from None
    elif settings.smtp_host:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    elif settings.app_env in {"development", "test"}:
        root = Path(settings.development_mail_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{secrets.token_hex(16)}.eml").write_text(message.as_string(), encoding="utf-8")
    else:
        raise HTTPException(503, "Email delivery is not configured")
