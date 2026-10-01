import hashlib
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .config import get_settings
from .customer_auth import (
    COOKIE,
    current_customer,
    digest,
    hash_password,
    invalidate_tokens,
    issue_token,
    password_matches,
    send_account_mail,
    valid_token,
)
from .customer_models import Customer, CustomerLicense, CustomerToken, PaymentEvent, Purchase
from .db import get_db
from .models import ActivationEvent, License, LicenseStatus, utcnow
from .payments import fulfill_checkout, identifier, reconcile_subscription, stripe_options

router = APIRouter()
_attempts: dict[str, list[float]] = {}
_attempt_lock = threading.Lock()
_dummy_hash = hash_password(secrets.token_urlsafe(32))


def limited(request: Request) -> None:
    # Per-process prototype guard. Replace with a shared limiter before scaling workers.
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _attempt_lock:
        for old_key in list(_attempts):
            _attempts[old_key] = [t for t in _attempts[old_key] if t > now - 60]
            if not _attempts[old_key]:
                del _attempts[old_key]
        hits = _attempts.setdefault(key, [])
        if len(hits) >= 20:
            raise HTTPException(429, "Too many attempts. Try again in a minute.")
        hits.append(now)


def same_origin(request: Request) -> None:
    if request.method in {"GET", "HEAD"}:
        return
    expected = urlsplit(get_settings().customer_portal_url)
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != f"{expected.scheme}://{expected.netloc}":
        raise HTTPException(403, "Invalid origin")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Invalid origin")


customer_api = APIRouter(prefix="/v1/customer", dependencies=[Depends(same_origin)])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class Registration(Credentials):
    company_name: str = Field(min_length=2, max_length=200)


class EmailInput(BaseModel):
    email: EmailStr


class TokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ResetInput(TokenInput):
    password: str = Field(min_length=12, max_length=256)


class CheckoutInput(BaseModel):
    seats: int = Field(ge=1, le=100000)


@customer_api.post("/register", dependencies=[Depends(limited)], status_code=202)
def register(payload: Registration, db: Session = Depends(get_db)) -> dict:
    email = str(payload.email).lower()
    if not db.scalar(select(Customer).where(Customer.email == email)):
        customer = Customer(email=email, company_name=payload.company_name,
                            password_hash=hash_password(payload.password))
        db.add(customer)
        try:
            db.flush()
            token = issue_token(db, customer.id, "verify", 60)
            db.commit()
        except IntegrityError:
            db.rollback()
        else:
            send_account_mail(email, token, "verify")
    return {"message": "Check your email to verify your account. Existing accounts can sign in or reset their password."}


@customer_api.post("/verify", dependencies=[Depends(limited)])
def verify_email(payload: TokenInput, db: Session = Depends(get_db)) -> dict:
    row = valid_token(db, payload.token, "verify")
    customer = db.get(Customer, row.customer_id)
    customer.verified_at = utcnow()
    invalidate_tokens(db, customer.id, "verify")
    db.commit()
    return {"message": "Email verified. You can now sign in."}


@customer_api.post("/resend-verification", dependencies=[Depends(limited)], status_code=202)
def resend_verification(payload: EmailInput, db: Session = Depends(get_db)) -> dict:
    customer = db.scalar(select(Customer).where(Customer.email == str(payload.email).lower()))
    if customer and not customer.verified_at:
        invalidate_tokens(db, customer.id, "verify")
        token = issue_token(db, customer.id, "verify", 60)
        db.commit()
        send_account_mail(customer.email, token, "verify")
    return {"message": "If verification is needed, an email has been sent."}


@customer_api.post("/login", dependencies=[Depends(limited)])
def login(payload: Credentials, response: Response, db: Session = Depends(get_db)) -> dict:
    customer = db.scalar(select(Customer).where(Customer.email == str(payload.email).lower()))
    matched = password_matches(customer.password_hash if customer else _dummy_hash, payload.password)
    if not customer or not matched:
        raise HTTPException(401, "Invalid credentials")
    if not customer.verified_at:
        raise HTTPException(403, "Verify your email before signing in")
    settings = get_settings()
    token = issue_token(db, customer.id, "session", settings.customer_session_hours * 60)
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", path="/",
                        secure=settings.customer_portal_url.startswith("https://"),
                        max_age=settings.customer_session_hours * 3600)
    return {"message": "Signed in"}


@customer_api.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    token = request.cookies.get(COOKIE)
    if token:
        row = db.get(CustomerToken, digest(token))
        if row:
            db.delete(row)
            db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"message": "Signed out"}


@customer_api.post("/forgot-password", dependencies=[Depends(limited)], status_code=202)
def forgot_password(payload: EmailInput, db: Session = Depends(get_db)) -> dict:
    customer = db.scalar(select(Customer).where(Customer.email == str(payload.email).lower()))
    if customer:
        invalidate_tokens(db, customer.id, "reset")
        token = issue_token(db, customer.id, "reset", 30)
        db.commit()
        send_account_mail(customer.email, token, "reset")
    return {"message": "If this account exists, a reset email has been sent."}


@customer_api.post("/reset-password", dependencies=[Depends(limited)])
def reset_password(payload: ResetInput, db: Session = Depends(get_db)) -> dict:
    row = valid_token(db, payload.token, "reset")
    customer = db.get(Customer, row.customer_id)
    customer.password_hash = hash_password(payload.password)
    invalidate_tokens(db, customer.id, "reset")
    invalidate_tokens(db, customer.id, "session")
    db.commit()
    return {"message": "Password updated. Sign in again."}


@customer_api.get("/me")
def me(customer: Customer = Depends(current_customer), db: Session = Depends(get_db)) -> dict:
    binding = db.get(CustomerLicense, customer.id)
    license = db.get(License, binding.license_id) if binding else None
    return {"email": customer.email, "company_name": customer.company_name,
            "license": {"id": license.id, "status": license.status.value,
                        "max_rdp_users": license.max_rdp_users,
                        "installation_id": license.installation_id} if license else None}


@customer_api.get("/plan")
def plan(_: Customer = Depends(current_customer)) -> dict:
    settings = get_settings()
    if not settings.stripe_rdp_price_id:
        raise HTTPException(503, "Plan pricing is not configured")
    price = stripe.Price.retrieve(settings.stripe_rdp_price_id, **stripe_options())
    if not price.get("active") or not price.get("recurring") or price.get("billing_scheme") != "per_unit":
        raise HTTPException(503, "Plan must be an active recurring per-user price")
    return {"currency": price["currency"], "unit_amount": price["unit_amount"],
            "interval": price["recurring"]["interval"],
            "interval_count": price["recurring"]["interval_count"]}


def paid_customer_license(customer: Customer, db: Session) -> License:
    binding = db.get(CustomerLicense, customer.id)
    license = db.get(License, binding.license_id) if binding else None
    if not license or license.status != LicenseStatus.active:
        raise HTTPException(403, 'An active paid license is required for this download')
    return license


def release_file() -> Path | None:
    settings = get_settings()
    if not settings.appliance_release_file or not settings.appliance_release_sha256:
        return None
    path = Path(settings.appliance_release_file)
    if not path.is_file() or not re.fullmatch('[a-fA-F0-9]{64}', settings.appliance_release_sha256):
        return None
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != settings.appliance_release_sha256.lower():
        raise HTTPException(503, 'Installer integrity check failed; try again later')
    return path


@customer_api.get('/downloads')
def downloads(customer: Customer = Depends(current_customer), db: Session = Depends(get_db)) -> dict:
    paid_customer_license(customer, db)
    path = release_file()
    return {'available': path is not None,
            'url': '/v1/customer/downloads/windows' if path else None,
            'sha256': get_settings().appliance_release_sha256 if path else None,
            'filename': 'bliss-mfa-windows-prototype.zip' if path else None}


@customer_api.get('/downloads/windows')
def download_windows(customer: Customer = Depends(current_customer), db: Session = Depends(get_db)) -> FileResponse:
    paid_customer_license(customer, db)
    path = release_file()
    if path is None:
        raise HTTPException(503, 'Windows installer is not available yet')
    return FileResponse(path, media_type='application/zip', filename='bliss-mfa-windows-prototype.zip',
                        headers={'Cache-Control': 'private, no-store'})


@customer_api.post("/checkout")
def checkout(payload: CheckoutInput, customer: Customer = Depends(current_customer),
             db: Session = Depends(get_db)) -> dict:
    # A row write serializes order creation on SQLite and PostgreSQL alike.
    db.execute(update(Customer).where(Customer.id == customer.id).values(company_name=customer.company_name))
    if db.get(CustomerLicense, customer.id):
        raise HTTPException(409, "Manage your existing subscription through billing")
    plan(customer)
    settings = get_settings()
    purchase = db.scalar(select(Purchase).where(Purchase.customer_id == customer.id,
                                                Purchase.status == "pending"))
    if purchase and purchase.session_id:
        session = stripe.checkout.Session.retrieve(purchase.session_id, **stripe_options())
        if session.get("status") == "open":
            return {"url": session["url"], "purchase_id": purchase.id}
        fulfill_checkout(db, purchase.session_id)
        db.commit()
        if purchase.status == "fulfilled":
            raise HTTPException(409, "Your purchase is already complete")
        if session.get("status") == "complete":
            raise HTTPException(409, "Your payment is still being confirmed")
        purchase = None
    if not purchase:
        purchase = Purchase(customer_id=customer.id, seats=payload.seats,
                            price_id=settings.stripe_rdp_price_id)
        db.add(purchase)
        db.commit()
    session = stripe.checkout.Session.create(
        mode="subscription", customer_email=customer.email, client_reference_id=purchase.id,
        line_items=[{"price": purchase.price_id, "quantity": purchase.seats}],
        success_url=settings.customer_portal_url.rstrip("/") + "/customer?checkout={CHECKOUT_SESSION_ID}",
        cancel_url=settings.customer_portal_url.rstrip("/") + "/customer?canceled=1",
        subscription_data={"metadata": {"bliss_customer_id": customer.id}},
        idempotency_key=purchase.id, **stripe_options())
    purchase.session_id = session["id"]
    db.commit()
    return {"url": session["url"], "purchase_id": purchase.id}


@customer_api.post("/purchases/{session_id}/refresh")
def refresh_purchase(session_id: str, customer: Customer = Depends(current_customer),
                     db: Session = Depends(get_db)) -> dict:
    purchase = db.scalar(select(Purchase).where(Purchase.session_id == session_id,
                                               Purchase.customer_id == customer.id))
    if not purchase:
        raise HTTPException(404, "Purchase not found")
    fulfill_checkout(db, session_id)
    db.commit()
    return {"status": purchase.status}


@customer_api.post("/activation-code")
def activation_code(customer: Customer = Depends(current_customer), db: Session = Depends(get_db)) -> dict:
    binding = db.get(CustomerLicense, customer.id)
    license = db.get(License, binding.license_id) if binding else None
    if not license:
        raise HTTPException(403, "Complete payment first")
    if license.status != LicenseStatus.active or license.installation_id:
        raise HTTPException(409, "An activation code is available only for an active, unbound license")
    code = "BLS-" + secrets.token_urlsafe(32)
    license.activation_code_hash = digest(code)
    db.add(ActivationEvent(license_id=license.id, event_type="customer.activation_code_issued"))
    db.commit()
    return {"activation_code": code}


@customer_api.post("/billing")
def billing(customer: Customer = Depends(current_customer), db: Session = Depends(get_db)) -> dict:
    binding = db.get(CustomerLicense, customer.id)
    license = db.get(License, binding.license_id) if binding else None
    if not license or not license.stripe_customer_id:
        raise HTTPException(404, "No billing account found")
    session = stripe.billing_portal.Session.create(customer=license.stripe_customer_id,
        return_url=get_settings().customer_portal_url.rstrip("/") + "/customer", **stripe_options())
    return {"url": session["url"]}


@router.post("/v1/webhooks/stripe")
async def webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    secret = get_settings().stripe_webhook_secret
    if not secret:
        raise HTTPException(503, "Webhook verification is not configured")
    try:
        event = stripe.Webhook.construct_event(await request.body(), request.headers.get("stripe-signature", ""), secret)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(400, "Invalid webhook signature or payload") from exc
    if db.get(PaymentEvent, event["id"]):
        return {"received": True}
    try:
        db.add(PaymentEvent(id=event["id"], event_type=event["type"]))
        db.flush()  # Unique event ID serializes duplicate delivery in this transaction.
        obj = event["data"]["object"]
        if event["type"] in {"checkout.session.completed", "checkout.session.async_payment_succeeded", "checkout.session.expired"}:
            fulfill_checkout(db, obj["id"])
        elif event["type"].startswith("customer.subscription."):
            reconcile_subscription(db, obj["id"])
        elif event["type"] in {"invoice.paid", "invoice.payment_failed"}:
            subscription_id = identifier(obj.get("subscription"))
            if not subscription_id:
                subscription_id = identifier(obj.get("parent", {}).get("subscription_details", {}).get("subscription"))
            if subscription_id:
                reconcile_subscription(db, subscription_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        if not db.get(PaymentEvent, event["id"]):
            raise HTTPException(503, "Fulfillment conflict; retry delivery")
    except OperationalError as exc:
        db.rollback()
        raise HTTPException(503, "Fulfillment temporarily unavailable; retry delivery") from exc
    return {"received": True}


@router.get("/customer")
def customer_page() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "customer.html", headers={"Cache-Control": "no-store"})


router.include_router(customer_api)
