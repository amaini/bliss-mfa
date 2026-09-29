from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Principal, get_principal
from .config import get_settings
from .db import get_db
from .models import (
    MembershipRole,
    Organization,
    OrganizationMembership,
    PortalUser,
    PortalUserStatus,
)


@dataclass(frozen=True)
class OrganizationAccess:
    principal: Principal
    organization_id: str
    role: str
    is_staff: bool

    @property
    def actor_id(self) -> str:
        return self.principal.actor_id


def _staff_role(principal: Principal) -> str | None:
    settings = get_settings()
    if settings.oidc_staff_admin_group in principal.groups:
        return "super_admin"
    if settings.oidc_staff_technician_group in principal.groups:
        return "technician"
    if settings.oidc_staff_billing_group in principal.groups:
        return "billing"
    return None


def _portal_user(db: Session, principal: Principal) -> PortalUser | None:
    user = db.scalar(
        select(PortalUser).where(PortalUser.external_subject == principal.subject)
    )
    if user:
        if principal.email and user.email != principal.email:
            user.email = principal.email
        return user

    if not principal.email:
        return None

    by_email = db.scalar(select(PortalUser).where(PortalUser.email == principal.email))
    if by_email:
        by_email.external_subject = principal.subject
        return by_email

    # Unknown identities may be represented locally, but they receive no tenant
    # access unless a membership already exists or Bliss staff groups authorize them.
    user = PortalUser(
        email=principal.email,
        status=PortalUserStatus.active,
        external_subject=principal.subject,
    )
    db.add(user)
    db.flush()
    return user


def _organization_access(
    organization_id: str,
    principal: Principal,
    db: Session,
) -> OrganizationAccess:
    if not db.get(Organization, organization_id):
        raise HTTPException(status_code=404, detail="Organization not found")

    staff_role = _staff_role(principal)
    if staff_role:
        return OrganizationAccess(
            principal=principal,
            organization_id=organization_id,
            role=staff_role,
            is_staff=True,
        )

    portal_user = _portal_user(db, principal)
    if not portal_user or portal_user.status != PortalUserStatus.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")

    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.portal_user_id == portal_user.id,
        )
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")

    return OrganizationAccess(
        principal=principal,
        organization_id=organization_id,
        role=membership.role.value,
        is_staff=False,
    )


def require_org_read(
    organization_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> OrganizationAccess:
    return _organization_access(organization_id, principal, db)


def require_org_manage(
    organization_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> OrganizationAccess:
    access = _organization_access(organization_id, principal, db)
    allowed = {
        "super_admin",
        "technician",
        MembershipRole.customer_admin.value,
        MembershipRole.customer_operator.value,
    }
    if access.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manage access required")
    return access


def require_org_admin(
    organization_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> OrganizationAccess:
    access = _organization_access(organization_id, principal, db)
    allowed = {"super_admin", MembershipRole.customer_admin.value}
    if access.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return access
