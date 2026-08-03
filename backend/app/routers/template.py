"""Universal Template Framework API.

Phase 1 (below, unchanged): runtime-only endpoints. The frontend's
DynamicTemplateForm renders from GET /templates/{module}/effective and
stores answers through the owning document's own endpoints (e.g.
POST /suppliers/requests), not directly here; the response read endpoint
exists so detail pages can show submitted answers without re-deriving them.

Phase 2 (bottom of file): admin authoring endpoints under /templates/admin,
added for the Template Admin UI. Template authoring was previously
seed-script-only ("no designer UI" per this docstring's earlier revision) --
these endpoints are the write path that replaces that. The path prefix
("admin", a literal segment) is chosen deliberately so it can never collide
with GET /templates/{module}/effective's {module} path parameter.
"""

from __future__ import annotations

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.template import (
    TemplateStateError,
    count_template_definitions,
    create_template_definition,
    delete_draft_template_definition,
    get_response_for_entity,
    get_template_definition_for_tenant,
    list_template_definitions,
    publish_template_definition,
    update_draft_template_definition,
)
from app.database.session import get_db
from app.models.user import User, UserRole
from app.schemas.template import (
    TemplateDefinitionCreate,
    TemplateDefinitionListResponse,
    TemplateDefinitionOut,
    TemplateDefinitionSummary,
    TemplatePublishRequest,
    TemplateResponseOut,
)
from app.services.template_engine import get_effective_template
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/templates", tags=["Templates"])


def _require_admin(current_user: User) -> None:
    """Same admin-gate pattern as routers/workflow.py, budget.py, approval.py:
    role=ADMINISTRATOR OR is_superuser."""
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can manage templates",
        )


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


# ---- Phase 2: Template Admin authoring ----


def _to_summary(definition) -> TemplateDefinitionSummary:
    return TemplateDefinitionSummary(
        id=definition.id,
        tenant_id=definition.tenant_id,
        module=definition.module,
        name=definition.name,
        description=definition.description,
        version=definition.version,
        status=definition.status,
        effective_date=definition.effective_date,
        expiry_date=definition.expiry_date,
        inheritance_mode=definition.inheritance_mode,
        created_at=definition.created_at,
        updated_at=definition.updated_at,
        section_count=len(definition.sections),
        question_count=sum(len(section.questions) for section in definition.sections),
    )


@router.get("/admin", response_model=TemplateDefinitionListResponse, summary="[Admin] List template definitions")
async def list_templates_admin(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    module: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
) -> TemplateDefinitionListResponse:
    _require_admin(current_user)
    definitions = await list_template_definitions(
        db, tenant_id=current_user.tenant_id, module=module, status_filter=status_filter, skip=skip, limit=limit
    )
    total = await count_template_definitions(
        db, tenant_id=current_user.tenant_id, module=module, status_filter=status_filter
    )
    return TemplateDefinitionListResponse(
        items=[_to_summary(d) for d in definitions], total=total, skip=skip, limit=limit
    )


@router.get("/admin/{template_id}", response_model=TemplateDefinitionOut, summary="[Admin] Get a template definition")
async def get_template_admin(
    template_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TemplateDefinitionOut:
    _require_admin(current_user)
    definition = await get_template_definition_for_tenant(db, template_id, tenant_id=current_user.tenant_id)
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return TemplateDefinitionOut.model_validate(definition)


@router.post(
    "/admin",
    response_model=TemplateDefinitionOut,
    status_code=status.HTTP_201_CREATED,
    summary="[Admin] Create a new template draft (or a new version of an existing name)",
)
async def create_template_admin(
    payload: TemplateDefinitionCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TemplateDefinitionOut:
    _require_admin(current_user)
    definition = await create_template_definition(
        db, payload, tenant_id=current_user.tenant_id, created_by=current_user.id
    )
    return TemplateDefinitionOut.model_validate(definition)


@router.put(
    "/admin/{template_id}",
    response_model=TemplateDefinitionOut,
    summary="[Admin] Edit a draft template in place",
)
async def update_template_admin(
    template_id: UUID,
    payload: TemplateDefinitionCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TemplateDefinitionOut:
    _require_admin(current_user)
    try:
        definition = await update_draft_template_definition(
            db, template_id, payload, tenant_id=current_user.tenant_id
        )
    except TemplateStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return TemplateDefinitionOut.model_validate(definition)


@router.post(
    "/admin/{template_id}/publish",
    response_model=TemplateDefinitionOut,
    summary="[Admin] Publish a draft (deprecates the prior published version, if any)",
)
async def publish_template_admin(
    template_id: UUID,
    payload: TemplatePublishRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TemplateDefinitionOut:
    _require_admin(current_user)
    try:
        definition = await publish_template_definition(
            db, template_id, tenant_id=current_user.tenant_id, effective_date=payload.effective_date
        )
    except TemplateStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return TemplateDefinitionOut.model_validate(definition)


@router.delete(
    "/admin/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="[Admin] Delete a draft template",
)
async def delete_template_admin(
    template_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    _require_admin(current_user)
    try:
        deleted = await delete_draft_template_definition(db, template_id, tenant_id=current_user.tenant_id)
    except TemplateStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
