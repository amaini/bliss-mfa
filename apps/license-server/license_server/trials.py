from datetime import UTC

from sqlalchemy import select

from .customer_models import CustomerTrial
from .models import LicenseStatus, utcnow


def trial_for(db, license_id):
    return db.scalar(select(CustomerTrial).where(CustomerTrial.license_id == license_id,
                                               CustomerTrial.converted_at.is_(None)))


def expiry(trial):
    value = trial.expires_at
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def entitlement_status(db, license):
    trial = trial_for(db, license.id)
    if trial and utcnow() >= expiry(trial):
        return LicenseStatus.expired
    return license.status
