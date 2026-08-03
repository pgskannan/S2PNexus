"""Universal Template Framework API (Phase 1).

Runtime endpoints only -- template authoring is seed-script-driven in this
batch (no designer UI). The frontend's DynamicTemplateForm renders from
GET /templates/{module}/effective and stores answers through the owning
document's own endpoints (e.g. POST /suppliers/requests), not directly here;
the response read endpoint exists so detail pages can show submitted answers
without re-deriving them.
"""

from __future__ import annotations

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.template import get_response_for_entity
from app.database.session import get_db
from app.models.user import User
from app.schemas.template import TemplateDefinitionOut, TemplateResponseOut
from app.services.template_engine import get_effective_template
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get("/{module}/effective", response_model=TemplateDefinitionOut, summary="Resolve the effective template for a module")
async def get_effective_template_endpoint(
    module: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> TemplateDefinitionOut:
    """Spec Section 4 inheritance: the current tenant's published template
    for the module if one exists, else the global published one."""
    template = await get_effective_template(db, module, tenant_id=current_user.tenant_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No published template for module '{module}'",
        )
    return TemplateDefinitionOut.model_validate(template)


@router.get("/responses/{entity_type}/{entity_id}", response_model=TemplateResponseOut, summary="Get the template response for an entity")
async def get_entity_response_endpoint(
    entity_type: str,
    entity_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> TemplateResponseOut:
    # get_response_for_entity matches this tenant's rows or untenanted rows,
    # never another tenant's -- no separate fallback lookup needed.
    response = await get_response_for_entity(db, entity_type, entity_id, tenant_id=current_user.tenant_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No template response for this entity")
    return TemplateResponseOut.model_validate(response)
