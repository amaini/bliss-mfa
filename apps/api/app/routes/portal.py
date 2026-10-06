from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, get_principal
from ..authorization import OrganizationAccess, require_org_admin
from ..db import get_db
from ..models import (
    MembershipRole,
    Organization,
    OrganizationMembership,
    PortalUser,
    PortalUserStatus,
)
from ..schemas import MembershipCreate, MembershipRead, MyOrganizationRead, PrincipalRead

router = APIRouter(tags=["portal"])


@router.get("/me", response_model=PrincipalRead)
def me(principal: Principal = Depends(get_principal)) -> PrincipalRead:
    return PrincipalRead(
        subject=principal.subject,
        email=principal.email,
        groups=sorted(principal.groups),
    )


@router.get("/me/organizations", response_model=list[MyOrganizationRead])
def my_organizations(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[MyOrganizationRead]:
    if not principal.email:
        return []

    portal_user = db.scalar(
        select(PortalUser).where(
            (PortalUser.external_subject == principal.subject)
            | (PortalUser.email == principal.email)
        )
    )
    if not portal_user:
        return []

    if portal_user.external_subject is None:
        portal_user.external_subject = principal.subject
        db.commit()

    rows = db.execute(
        select(OrganizationMembership, Organization)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(OrganizationMembership.portal_user_id == portal_user.id)
        .order_by(Organization.name)
    ).all()

    return [
        MyOrganizationRead(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            role=membership.role.value,
            seat_limit=organization.seat_limit,
        )
        for membership, organization in rows
    ]


@router.get(
    "/organizations/{organization_id}/memberships",
    response_model=list[MembershipRead],
)
def list_memberships(
    organization_id: str,
    _: OrganizationAccess = Depends(require_org_admin),
    db: Session = Depends(get_db),
) -> list[MembershipRead]:
    rows = db.execute(
        select(OrganizationMembership, PortalUser)
        .join(PortalUser, PortalUser.id == OrganizationMembership.portal_user_id)
        .where(OrganizationMembership.organization_id == organization_id)
        .order_by(PortalUser.email)
    ).all()

    return [
        MembershipRead(
            id=membership.id,
            organization_id=organization_id,
            portal_user_id=user.id,
            email=user.email,
            role=membership.role.value,
            status=user.status.value,
        )
        for membership, user in rows
    ]


@router.post(
    "/organizations/{organization_id}/memberships",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def create_membership(
    organization_id: str,
    payload: MembershipCreate,
    _: OrganizationAccess = Depends(require_org_admin),
    db: Session = Depends(get_db),
) -> MembershipRead:
    email = str(payload.email).lower()
    portal_user = db.scalar(select(PortalUser).where(PortalUser.email == email))
    if not portal_user:
        portal_user = PortalUser(
            email=email,
            status=PortalUserStatus.invited,
        )
        db.add(portal_user)
        db.flush()

    existing = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.portal_user_id == portal_user.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Membership already exists")

    membership = OrganizationMembership(
        organization_id=organization_id,
        portal_user_id=portal_user.id,
        role=MembershipRole(payload.role),
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)

    return MembershipRead(
        id=membership.id,
        organization_id=organization_id,
        portal_user_id=portal_user.id,
        email=portal_user.email,
        role=membership.role.value,
        status=portal_user.status.value,
    )


@router.delete(
    "/organizations/{organization_id}/memberships/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_membership(
    organization_id: str,
    membership_id: str,
    _: OrganizationAccess = Depends(require_org_admin),
    db: Session = Depends(get_db),
) -> None:
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == organization_id,
        )
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    db.delete(membership)
    db.commit()
