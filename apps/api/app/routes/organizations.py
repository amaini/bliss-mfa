from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Organization
from ..schemas import OrganizationCreate, OrganizationRead
from ..auth import Principal, require_admin_principal, require_staff_principal


router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
    dependencies=[Depends(require_staff_principal)],
)


@router.get("", response_model=list[OrganizationRead])
def list_organizations(db: Session = Depends(get_db)) -> list[Organization]:
    return list(db.scalars(select(Organization).order_by(Organization.name)))


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    _: Principal = Depends(require_admin_principal),
    db: Session = Depends(get_db),
) -> Organization:
    if db.scalar(select(Organization).where(Organization.slug == payload.slug)):
        raise HTTPException(status_code=409, detail="Organization slug already exists")

    organization = Organization(
        name=payload.name,
        slug=payload.slug,
        seat_limit=payload.seat_limit,
    )
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization
