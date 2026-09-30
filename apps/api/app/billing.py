from __future__ import annotations

import hashlib
import secrets

import stripe

from .config import get_settings


def hash_onboarding_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_onboarding_token() -> str:
    return secrets.token_urlsafe(48)


def get_price_id(plan_code: str) -> str:
    settings = get_settings()
    mapping = {
        "starter": settings.stripe_price_starter,
        "business": settings.stripe_price_business,
        "business_plus": settings.stripe_price_business_plus,
    }
    price_id = mapping.get(plan_code)
    if not price_id:
        raise RuntimeError(f"Stripe price is not configured for plan: {plan_code}")
    return price_id


def configure_stripe() -> None:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise RuntimeError("Stripe secret key is not configured")
    stripe.api_key = settings.stripe_secret_key
