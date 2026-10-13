"""Supplier knowledge graph + supplier certification endpoints (HackFW SRM track).

GET    /supplier-graph                      nodes/edges/stats for the caller's tenant
GET    /supplier-graph/sources              "who can ship this part, certified, what's open, when paid"
GET    /supplier-certifications             list (optionally for one supplier)
POST   /supplier-certifications             record a certificate (supplier/category/procurement roles)
DELETE /supplier-certifications/{id}        remove a tenant-owned certificate

See app.services.supplier_graph for how the graph is assembled and scoped.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.supplier import Supplier
from app.models.supplier_certification import SupplierCertification
from app.models.user import User, UserRole
from app.services.supplier_graph import build_supplier_graph, certification_status, find_certified_sources
from app.utils.dependencies import get_current_active_user

router = APIRouter(tags=["Supplier Graph"])

_CERT_EDITOR_ROLES = {
    UserRole.ADMINISTRATOR,
    UserRole.PROCUREMENT_MANAGER,
    UserRole.SUPPLIER_MANAGER,
    UserRole.CATEGORY_MANAGER,
}


def _require_cert_editor(user: User) -> None:
    if user.is_superuser or user.role in _CERT_EDITOR_ROLES:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only administrators, procurement, supplier or category managers can change certifications",
    )


class SupplierCertificationCreate(BaseModel):
    supplier_id: UUID
    cert_type: str = Field(min_length=2, max_length=100)
    certificate_number: str | None = Field(default=None, max_length=100)
    issuing_body: str | None = Field(default=None, max_length=255)
    scope: str | None = None
    issued_on: date | None = None
    expires_on: date | None = None

    @model_validator(mode="after")
    def _dates_in_order(self):
        if self.issued_on and self.expires_on and self.expires_on < self.issued_on:
            raise ValueError("expires_on must be on or after issued_on")
        self.cert_type = self.cert_type.strip()
        return self


def _cert_out(cert: SupplierCertification, today: date) -> dict:
    return {
        "id": str(cert.id),
        "supplier_id": str(cert.supplier_id),
        "supplier_name": cert.supplier.name if cert.supplier is not None else None,
        "cert_type": cert.cert_type,
        "certificate_number": cert.certificate_number,
        "issuing_body": cert.issuing_body,
        "scope": cert.scope,
        "issued_on": cert.issued_on.isoformat() if cert.issued_on else None,
        "expires_on": cert.expires_on.isoformat() if cert.expires_on else None,
        "status": certification_status(cert.expires_on, today),
        "tenant_owned": cert.tenant_id is not None,
    }


@router.get("/supplier-graph")
async def get_supplier_graph(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    supplier_id: UUID | None = Query(default=None),
    commodity: str | None = Query(default=None, max_length=100, description="UNSPSC prefix or title text"),
    cert_type: str | None = Query(default=None, max_length=100),
    include_documents: bool = Query(default=True, description="Include open PO and invoice nodes"),
):
    return await build_supplier_graph(
        db,
        current_user.tenant_id,
        supplier_id=supplier_id,
        commodity=commodity,
        cert_type=cert_type,
        include_documents=include_documents,
    )


@router.get("/supplier-graph/sources")
async def get_certified_sources(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    commodity: str = Query(min_length=1, max_length=100, description="UNSPSC prefix or title text"),
    cert_type: str | None = Query(default=None, max_length=100),
):
    return await find_certified_sources(db, current_user.tenant_id, commodity=commodity, cert_type=cert_type)


@router.get("/supplier-certifications")
async def list_supplier_certifications(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    supplier_id: UUID | None = Query(default=None),
):
    q = select(SupplierCertification)
    if current_user.tenant_id is not None:
        q = q.where(
            or_(SupplierCertification.tenant_id.is_(None), SupplierCertification.tenant_id == current_user.tenant_id)
        )
    if supplier_id is not None:
        q = q.where(SupplierCertification.supplier_id == supplier_id)
    q = q.order_by(SupplierCertification.expires_on.asc().nulls_last())
    today = date.today()
    return [_cert_out(c, today) for c in (await db.execute(q)).scalars().all()]


@router.post("/supplier-certifications", status_code=status.HTTP_201_CREATED)
async def create_supplier_certification(
    payload: SupplierCertificationCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_cert_editor(current_user)
    supplier = await db.get(Supplier, payload.supplier_id)
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    cert = SupplierCertification(
        **payload.model_dump(),
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
    )
    db.add(cert)
    await db.commit()
    await db.refresh(cert)
    return _cert_out(cert, date.today())


@router.delete("/supplier-certifications/{cert_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_supplier_certification(
    cert_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_cert_editor(current_user)
    cert = await db.get(SupplierCertification, cert_id)
    # Another tenant's certificate is reported as not found, never as forbidden,
    # so its existence isn't leaked. Shared (NULL-tenant) rows need a superuser.
    if cert is None or (
        cert.tenant_id is not None and current_user.tenant_id is not None and cert.tenant_id != current_user.tenant_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certification not found")
    if cert.tenant_id is None and current_user.tenant_id is not None and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Shared certifications can only be removed by a superuser")
    await db.delete(cert)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
