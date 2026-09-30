"""Fulfill verified Checkout sessions using current Stripe subscription state."""
import stripe
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .customer_auth import digest
from .customer_models import Customer, CustomerLicense, Purchase
from .models import ActivationEvent, License, LicenseStatus, LicenseType


def stripe_options() -> dict:
    key = get_settings().stripe_secret_key
    if not key:
        raise HTTPException(503, "Payments are not configured")
    return {"api_key": key}


def identifier(value) -> str | None:
    return value.get("id") if isinstance(value, dict) else value


def subscription_seats(subscription: dict, price_id: str) -> int:
    items = subscription.get("items", {}).get("data", [])
    if len(items) != 1 or identifier(items[0].get("price")) != price_id:
        raise HTTPException(409, "Subscription price does not match the purchased plan")
    quantity = items[0].get("quantity")
    if type(quantity) is not int or not 1 <= quantity <= 100000:
        raise HTTPException(409, "Invalid subscription seat quantity")
    return quantity


def current_subscription(subscription_id: str) -> dict:
    return stripe.Subscription.retrieve(subscription_id, expand=["latest_invoice"], **stripe_options())


def reconcile_subscription(db: Session, subscription_id: str) -> None:
    binding = db.scalar(select(CustomerLicense).where(CustomerLicense.subscription_id == subscription_id))
    if not binding:
        return
    license = db.get(License, binding.license_id)
    subscription = current_subscription(subscription_id)
    if identifier(subscription.get("customer")) != license.stripe_customer_id:
        raise HTTPException(409, "Subscription customer mismatch")
    state = subscription.get("status")
    invoice = subscription.get("latest_invoice")
    if state == "active" and isinstance(invoice, dict) and invoice.get("status") == "paid":
        license.max_rdp_users = subscription_seats(subscription, get_settings().stripe_rdp_price_id)
        license.status = LicenseStatus.active
    elif state == "canceled":
        license.status = LicenseStatus.expired
    else:
        license.status = LicenseStatus.suspended
    db.add(ActivationEvent(license_id=license.id, event_type="billing.subscription_reconciled",
                           detail=str(state)))


def fulfill_checkout(db: Session, session_id: str) -> Purchase | None:
    purchase = db.scalar(select(Purchase).where(Purchase.session_id == session_id).with_for_update())
    if not purchase:
        return None  # Checkout sessions belonging to another product are ignored.
    session = stripe.checkout.Session.retrieve(session_id, **stripe_options())
    if session.get("client_reference_id") != purchase.id or session.get("mode") != "subscription":
        raise HTTPException(409, "Checkout reference mismatch")
    if session.get("status") == "expired":
        if purchase.status != "fulfilled":
            purchase.status = "expired"
        return purchase
    if session.get("status") != "complete" or session.get("payment_status") != "paid":
        return purchase
    subscription_id = identifier(session.get("subscription"))
    if not subscription_id:
        raise HTTPException(409, "Paid checkout has no subscription")
    subscription = current_subscription(subscription_id)
    if identifier(subscription.get("customer")) != identifier(session.get("customer")):
        raise HTTPException(409, "Checkout customer mismatch")
    seats = subscription_seats(subscription, purchase.price_id)
    if seats != purchase.seats:
        # After fulfillment, changes are managed by subscription reconciliation.
        if purchase.status != "fulfilled":
            raise HTTPException(409, "Checkout seat quantity mismatch")
    binding = db.get(CustomerLicense, purchase.customer_id)
    if binding:
        if binding.subscription_id != subscription_id:
            raise HTTPException(409, "Customer already owns another subscription")
    else:
        customer = db.get(Customer, purchase.customer_id)
        license = License(customer_name=customer.company_name, customer_email=customer.email,
                          license_type=LicenseType.online, max_rdp_users=seats,
                          stripe_customer_id=identifier(session.get("customer")),
                          stripe_subscription_id=subscription_id)
        db.add(license)
        db.flush()
        db.add(CustomerLicense(customer_id=customer.id, license_id=license.id,
                               subscription_id=subscription_id))
        db.add(ActivationEvent(license_id=license.id, event_type="billing.checkout_fulfilled",
                               detail=digest(session_id)))
        db.flush()
    purchase.status = "fulfilled"
    reconcile_subscription(db, subscription_id)
    return purchase
