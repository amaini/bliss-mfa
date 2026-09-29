from __future__ import annotations

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
from ..models import (
    MembershipRole,
    Organization,
    OrganizationMembership,
    PendingSignup,
    PortalUser,
    PortalUserStatus,
    SignupStatus,
    StripeWebhookEvent,
    Subscription,
    SubscriptionStatus,
)
from ..schemas import (
    CheckoutCreateRead,
    CheckoutCreateRequest,
    OnboardingCompleteRead,
    OnboardingCompleteRequest,
    OnboardingStatusRead,
)


router = APIRouter(prefix="/billing", tags=["billing"])

PLAN_SEATS = {
    "starter": 10,
    "business": 50,
    "business_plus": 100,
}


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
    except Exception as exc:
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


@router.get("/onboarding-status", response_model=OnboardingStatusRead)
def onboarding_status(
    token: str = Query(min_length=32, max_length=512),
    db: Session = Depends(get_db),
) -> OnboardingStatusRead:
    signup = db.scalar(
        select(PendingSignup).where(
            PendingSignup.onboarding_token_hash == hash_onboarding_token(token)
        )
    )
    if not signup:
        raise HTTPException(status_code=404, detail="Onboarding session not found")

    return OnboardingStatusRead(
        status=signup.status.value,
        company_name=signup.company_name,
        email=signup.email,
        plan_code=signup.plan_code,
    )


@router.post("/complete-onboarding", response_model=OnboardingCompleteRead)
def complete_onboarding(
    payload: OnboardingCompleteRequest,
    db: Session = Depends(get_db),
) -> OnboardingCompleteRead:
    signup = db.scalar(
        select(PendingSignup).where(
            PendingSignup.onboarding_token_hash
            == hash_onboarding_token(payload.onboarding_token)
        )
    )
    if not signup:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
    if signup.status == SignupStatus.completed:
        raise HTTPException(status_code=409, detail="Onboarding already completed")
    if signup.status != SignupStatus.paid_pending_setup:
        raise HTTPException(status_code=409, detail="Payment is not confirmed")

    if db.scalar(select(Organization).where(Organization.slug == payload.organization_slug)):
        raise HTTPException(status_code=409, detail="Organization slug already exists")

    seat_limit = PLAN_SEATS[signup.plan_code]
    organization = Organization(
        name=signup.company_name,
        slug=payload.organization_slug,
        seat_limit=seat_limit,
    )
    db.add(organization)
    db.flush()

    subscription = Subscription(
        organization_id=organization.id,
        stripe_customer_id=signup.stripe_customer_id,
        stripe_subscription_id=signup.stripe_subscription_id,
        stripe_price_id=get_price_id(signup.plan_code),
        plan_code=signup.plan_code,
        status=SubscriptionStatus.active,
    )
    db.add(subscription)

    portal_user = db.scalar(select(PortalUser).where(PortalUser.email == signup.email.lower()))
    if not portal_user:
        portal_user = PortalUser(
            email=signup.email.lower(),
            status=PortalUserStatus.invited,
        )
        db.add(portal_user)
        db.flush()

    membership = OrganizationMembership(
        organization_id=organization.id,
        portal_user_id=portal_user.id,
        role=MembershipRole.customer_admin,
    )
    db.add(membership)

    signup.status = SignupStatus.completed
    db.commit()

    return OnboardingCompleteRead(
        organization_id=organization.id,
        organization_slug=organization.slug,
        seat_limit=organization.seat_limit,
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
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook") from exc

    event_id = event["id"]
    if db.get(StripeWebhookEvent, event_id):
        return {"received": True}

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        signup_id = session.get("client_reference_id") or session.get("metadata", {}).get(
            "signup_id"
        )
        if signup_id:
            signup = db.get(PendingSignup, signup_id)
            if signup:
                signup.stripe_checkout_session_id = session.get("id")
                signup.stripe_customer_id = session.get("customer")
                signup.stripe_subscription_id = session.get("subscription")
                signup.status = SignupStatus.paid_pending_setup

    db.add(StripeWebhookEvent(id=event_id, event_type=event["type"]))
    db.commit()
    return {"received": True}
