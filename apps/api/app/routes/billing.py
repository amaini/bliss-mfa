from __future__ import annotations

import json

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..billing import (
    configure_stripe,
    generate_onboarding_token,
    get_price_id,
    hash_onboarding_token,
)
from ..config import get_settings
from ..db import get_db
from ..models import PendingSignup, SignupStatus
from ..schemas import CheckoutCreateRead, CheckoutCreateRequest


router = APIRouter(prefix="/billing", tags=["billing"])


@router.post(
    "/checkout",
    response_model=CheckoutCreateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_checkout(
    payload: CheckoutCreateRequest,
    db: Session = Depends(get_db),
) -> CheckoutCreateRead:
    try:
        configure_stripe()
        price_id = get_price_id(payload.plan_code)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    raw_onboarding_token = generate_onboarding_token()
    signup = PendingSignup(
        company_name=payload.company_name,
        email=str(payload.email),
        plan_code=payload.plan_code,
        onboarding_token_hash=hash_onboarding_token(raw_onboarding_token),
        status=SignupStatus.checkout_created,
    )
    db.add(signup)
    db.flush()

    settings = get_settings()
    success_url = (
        f"{settings.portal_base_url.rstrip('/')}/onboarding"
        f"?token={raw_onboarding_token}&session_id={{CHECKOUT_SESSION_ID}}"
    )
    cancel_url = f"{settings.portal_base_url.rstrip('/')}/plans?checkout=cancelled"

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=str(payload.email),
            client_reference_id=signup.id,
            metadata={
                "signup_id": signup.id,
                "plan_code": payload.plan_code,
            },
            subscription_data={
                "metadata": {
                    "signup_id": signup.id,
                    "plan_code": payload.plan_code,
                }
            },
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
        )
    except stripe.StripeError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="Unable to create checkout session") from exc

    signup.stripe_checkout_session_id = session.id
    db.commit()

    if not session.url:
        raise HTTPException(status_code=502, detail="Stripe did not return a checkout URL")

    return CheckoutCreateRead(
        checkout_url=session.url,
        checkout_session_id=session.id,
    )


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, bool]:
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Stripe webhook is not configured")

    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=settings.stripe_webhook_secret,
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook") from exc

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        signup_id = session.get("client_reference_id") or session.get("metadata", {}).get("signup_id")
        if signup_id:
            signup = db.get(PendingSignup, signup_id)
            if signup:
                signup.stripe_checkout_session_id = session.get("id")
                signup.stripe_customer_id = session.get("customer")
                signup.stripe_subscription_id = session.get("subscription")
                signup.status = SignupStatus.paid_pending_setup
                db.commit()

    return {"received": True}
