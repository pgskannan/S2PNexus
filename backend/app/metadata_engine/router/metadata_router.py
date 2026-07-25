"""Metadata Engine API router."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_tenant_id, require_permission
from app.database.database import get_db
from app.metadata_engine.schemas import (
    MetadataAuditEventListResponse,
    MetadataAuditEventResponse,
    MetadataFieldCreate,
    MetadataFieldListResponse,
    MetadataFieldResponse,
    MetadataFieldUpdate,
    MetadataLayoutCreate,
    MetadataLayoutListResponse,
    MetadataLayoutResponse,
    MetadataLayoutUpdate,
    MetadataObjectCreate,
    MetadataObjectListResponse,
    MetadataObjectResponse,
    MetadataObjectUpdate,
    MetadataValueCreate,
    MetadataValueListResponse,
    MetadataValueResponse,
    MetadataValueUpdate,
    MetadataPicklistCreate,
    MetadataPicklistResponse,
    MetadataPicklistUpdate,
)
from app.metadata_engine.services.metadata_service import MetadataService
from app.models.user import User

router = APIRouter(prefix="/metadata", tags=["Metadata"])
service = MetadataService()


@router.post("/picklists", response_model=MetadataPicklistResponse, status_code=status.HTTP_201_CREATED, summary="Create metadata picklist")
async def create_metadata_picklist(
    picklist_in: MetadataPicklistCreate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataPicklistResponse:
    picklist = await service.create_picklist(db, tenant_id, picklist_in.model_dump(), current_user.id)
    return MetadataPicklistResponse.model_validate(picklist)


@router.get("/picklists", response_model=list[MetadataPicklistResponse], summary="List metadata picklists")
async def list_metadata_picklists(
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> list[MetadataPicklistResponse]:
    picklists = await service.list_picklists(db, tenant_id)
    return [MetadataPicklistResponse.model_validate(item) for item in picklists]


@router.patch("/picklists/{picklist_id}", response_model=MetadataPicklistResponse, summary="Update metadata picklist")
async def update_metadata_picklist(
    picklist_id: UUID,
    picklist_update: MetadataPicklistUpdate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataPicklistResponse:
    picklist = await service.update_picklist(db, picklist_id, tenant_id, picklist_update.model_dump(exclude_unset=True))
    return MetadataPicklistResponse.model_validate(picklist)


@router.delete("/picklists/{picklist_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete metadata picklist")
async def delete_metadata_picklist(
    picklist_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.delete_picklist(db, picklist_id, tenant_id)


@router.post(
    "/fields",
    response_model=MetadataFieldResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create metadata field",
)
async def create_metadata_field(
    field_in: MetadataFieldCreate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataFieldResponse:
    field = await service.create_field(db, tenant_id, field_in.model_dump(), created_by=current_user.id)
    return MetadataFieldResponse.model_validate(field)


@router.get("/fields", response_model=MetadataFieldListResponse, summary="List metadata fields")
async def list_metadata_fields(
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: bool | None = Query(None),
    search: str | None = Query(None, max_length=100),
) -> MetadataFieldListResponse:
    fields, total = await service.list_fields(db, tenant_id, skip=skip, limit=limit, is_active=is_active, search=search)
    return MetadataFieldListResponse(
        items=[MetadataFieldResponse.model_validate(f) for f in fields],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/fields/{field_id}", response_model=MetadataFieldResponse, summary="Get metadata field")
async def get_metadata_field(
    field_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataFieldResponse:
    try:
        field = await service.get_field(db, field_id, tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MetadataFieldResponse.model_validate(field)


@router.patch("/fields/{field_id}", response_model=MetadataFieldResponse, summary="Update metadata field")
async def update_metadata_field(
    field_id: UUID,
    field_update: MetadataFieldUpdate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataFieldResponse:
    try:
        field = await service.update_field(db, field_id, field_update.model_dump(exclude_unset=True), tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MetadataFieldResponse.model_validate(field)


@router.delete("/fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete metadata field")
async def delete_metadata_field(
    field_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.delete_field(db, field_id, tenant_id)


@router.post(
    "/values",
    response_model=MetadataValueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create metadata value",
)
async def create_metadata_value(
    value_in: MetadataValueCreate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataValueResponse:
    value = await service.create_value(db, tenant_id, value_in.model_dump(), created_by=current_user.id)
    return MetadataValueResponse.model_validate(value)


@router.get("/values", response_model=MetadataValueListResponse, summary="List metadata values")
async def list_metadata_values(
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    entity_type: str | None = Query(None),
    entity_id: UUID | None = Query(None),
    field_id: UUID | None = Query(None),
) -> MetadataValueListResponse:
    values, total = await service.list_values(
        db,
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        field_id=field_id,
        skip=skip,
        limit=limit,
    )
    return MetadataValueListResponse(
        items=[MetadataValueResponse.model_validate(v) for v in values],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/values/{value_id}", response_model=MetadataValueResponse, summary="Get metadata value")
async def get_metadata_value(
    value_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataValueResponse:
    try:
        value = await service.get_value(db, value_id, tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MetadataValueResponse.model_validate(value)


@router.patch("/values/{value_id}", response_model=MetadataValueResponse, summary="Update metadata value")
async def update_metadata_value(
    value_id: UUID,
    value_update: MetadataValueUpdate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataValueResponse:
    try:
        value = await service.update_value(db, value_id, value_update.model_dump(exclude_unset=True), tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MetadataValueResponse.model_validate(value)


@router.delete("/values/{value_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete metadata value")
async def delete_metadata_value(
    value_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.delete_value(db, value_id, tenant_id)


@router.post(
    "/objects/register",
    response_model=MetadataObjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register metadata object",
)
async def register_metadata_object(
    object_in: MetadataObjectCreate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataObjectResponse:
    metadata_object = await service.register_object(db, tenant_id, object_in.model_dump(), current_user.id)
    return MetadataObjectResponse.model_validate(metadata_object)


@router.post(
    "/objects",
    response_model=MetadataObjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create metadata object",
)
async def create_metadata_object(
    object_in: MetadataObjectCreate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataObjectResponse:
    metadata_object = await service.create_object(db, tenant_id, object_in.model_dump(), created_by=current_user.id)
    return MetadataObjectResponse.model_validate(metadata_object)


@router.get("/objects", response_model=MetadataObjectListResponse, summary="List metadata objects")
async def list_metadata_objects(
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str | None = Query(None, max_length=100),
) -> MetadataObjectListResponse:
    objects, total = await service.list_objects(db, tenant_id=tenant_id, skip=skip, limit=limit, search=search)
    return MetadataObjectListResponse(
        items=[MetadataObjectResponse.model_validate(obj) for obj in objects],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/objects/{object_id}", response_model=MetadataObjectResponse, summary="Get metadata object")
async def get_metadata_object(
    object_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataObjectResponse:
    try:
        metadata_object = await service.get_object(db, object_id, tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MetadataObjectResponse.model_validate(metadata_object)


@router.patch("/objects/{object_id}", response_model=MetadataObjectResponse, summary="Update metadata object")
async def update_metadata_object(
    object_id: UUID,
    object_update: MetadataObjectUpdate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataObjectResponse:
    try:
        metadata_object = await service.update_object(db, object_id, object_update.model_dump(exclude_unset=True), tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MetadataObjectResponse.model_validate(metadata_object)


@router.delete("/objects/{object_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete metadata object")
async def delete_metadata_object(
    object_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.delete_object(db, object_id, tenant_id)


@router.post(
    "/layouts/register",
    response_model=MetadataLayoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register metadata layout",
)
async def register_metadata_layout(
    layout_in: MetadataLayoutCreate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataLayoutResponse:
    layout = await service.register_layout(db, tenant_id, layout_in.model_dump(), current_user.id)
    return MetadataLayoutResponse.model_validate(layout)


@router.post(
    "/layouts",
    response_model=MetadataLayoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create metadata layout",
)
async def create_metadata_layout(
    layout_in: MetadataLayoutCreate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataLayoutResponse:
    layout = await service.create_layout(db, tenant_id, layout_in.model_dump(), created_by=current_user.id)
    return MetadataLayoutResponse.model_validate(layout)


@router.get("/layouts", response_model=MetadataLayoutListResponse, summary="List metadata layouts")
async def list_metadata_layouts(
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    metadata_object_id: UUID | None = Query(None),
    is_active: bool | None = Query(None),
) -> MetadataLayoutListResponse:
    layouts, total = await service.list_layouts(
        db,
        metadata_object_id=metadata_object_id,
        tenant_id=tenant_id,
        skip=skip,
        limit=limit,
        is_active=is_active,
    )
    return MetadataLayoutListResponse(
        items=[MetadataLayoutResponse.model_validate(layout) for layout in layouts],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/layouts/{layout_id}", response_model=MetadataLayoutResponse, summary="Get metadata layout")
async def get_metadata_layout(
    layout_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataLayoutResponse:
    try:
        layout = await service.get_layout(db, layout_id, tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MetadataLayoutResponse.model_validate(layout)


@router.patch("/layouts/{layout_id}", response_model=MetadataLayoutResponse, summary="Update metadata layout")
async def update_metadata_layout(
    layout_id: UUID,
    layout_update: MetadataLayoutUpdate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataLayoutResponse:
    try:
        layout = await service.update_layout(db, layout_id, layout_update.model_dump(exclude_unset=True), tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MetadataLayoutResponse.model_validate(layout)


@router.delete("/layouts/{layout_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete metadata layout")
async def delete_metadata_layout(
    layout_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.delete_layout(db, layout_id, tenant_id)


@router.post(
    "/fields/register",
    response_model=MetadataFieldResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register metadata field",
)
async def register_metadata_field(
    field_in: MetadataFieldCreate,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataFieldResponse:
    field = await service.register_field(db, tenant_id, field_in.model_dump(), current_user.id)
    return MetadataFieldResponse.model_validate(field)


@router.post(
    "/validate",
    response_model=dict,
    summary="Validate metadata payload",
)
async def validate_metadata_payload(
    payload: dict[str, Any],
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await service.validate_metadata(db, tenant_id, payload)


@router.post(
    "/versions/create",
    response_model=MetadataLayoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create metadata version",
)
async def create_metadata_version(
    metadata_object_id: Annotated[UUID, Query(...)],
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataLayoutResponse:
    layout = await service.create_version(db, tenant_id, metadata_object_id, current_user.id)
    return MetadataLayoutResponse.model_validate(layout)


@router.post(
    "/versions/create/{object_id}",
    response_model=MetadataLayoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create metadata version",
)
async def create_metadata_version_path(
    object_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> MetadataLayoutResponse:
    layout = await service.create_version(db, tenant_id, object_id, current_user.id)
    return MetadataLayoutResponse.model_validate(layout)


@router.post(
    "/versions/publish/{object_id}",
    response_model=MetadataLayoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish metadata layout version",
)
async def publish_metadata_version(
    object_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    version: int = Query(...),
    db: AsyncSession = Depends(get_db),
) -> MetadataLayoutResponse:
    layout = await service.publish_version(db, tenant_id, object_id, version, current_user.id)
    return MetadataLayoutResponse.model_validate(layout)


@router.post(
    "/versions/rollback/{object_id}",
    response_model=MetadataLayoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Rollback metadata layout version",
)
async def rollback_metadata_version(
    object_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    version: int = Query(...),
    db: AsyncSession = Depends(get_db),
) -> MetadataLayoutResponse:
    layout = await service.rollback_version(db, tenant_id, object_id, version, current_user.id)
    return MetadataLayoutResponse.model_validate(layout)


@router.post(
    "/versions/restore/{object_id}",
    response_model=MetadataLayoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Restore metadata layout version",
)
async def restore_metadata_version(
    object_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    version: int = Query(...),
    db: AsyncSession = Depends(get_db),
) -> MetadataLayoutResponse:
    layout = await service.restore_version(db, tenant_id, object_id, version, current_user.id)
    return MetadataLayoutResponse.model_validate(layout)


@router.post(
    "/import",
    response_model=dict,
    summary="Import metadata payload",
)
async def import_metadata_payload(
    payload: dict[str, Any],
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await service.import_metadata(db, tenant_id, payload, current_user.id)


@router.get(
    "/export/{object_id}",
    response_model=dict,
    summary="Export metadata for an object",
)
async def export_metadata_payload(
    object_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await service.export_metadata(db, tenant_id, object_id)


@router.post(
    "/cache/refresh",
    response_model=dict,
    summary="Refresh metadata cache",
)
async def refresh_metadata_cache(
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
) -> dict[str, Any]:
    return await service.refresh_cache(tenant_id)


@router.post(
    "/cache/clear",
    response_model=dict,
    summary="Clear metadata cache",
)
async def clear_metadata_cache(
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
) -> dict[str, Any]:
    return await service.clear_cache(tenant_id)


@router.get("/cache/metrics", response_model=dict[str, int], summary="Get metadata cache metrics")
async def get_metadata_cache_metrics(
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
) -> dict[str, int]:
    return await service.cache_service.metrics()


@router.get(
    "/versions",
    response_model=list[dict[str, Any]],
    summary="List metadata versions",
)
async def list_metadata_versions(
    metadata_object_id: Annotated[UUID, Query(...)],
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    return await service.list_versions(db, tenant_id, metadata_object_id)


@router.get(
    "/versions/history",
    response_model=list[dict[str, Any]],
    summary="Get metadata version history",
)
async def get_metadata_version_history(
    metadata_object_id: Annotated[UUID, Query(...)],
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    return await service.get_version_history(db, tenant_id, metadata_object_id)


@router.get(
    "/versions/diff",
    response_model=dict[str, Any],
    summary="Compare metadata versions",
)
async def diff_metadata_versions(
    from_version: Annotated[int, Query(...)],
    to_version: Annotated[int, Query(...)],
    metadata_object_id: Annotated[UUID, Query(...)],
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from_layout = await service.version_service.repository.get_version_or_raise(db, metadata_object_id, from_version, tenant_id=tenant_id)
    to_layout = await service.version_service.repository.get_version_or_raise(db, metadata_object_id, to_version, tenant_id=tenant_id)
    return await service.compare_versions(from_layout, to_layout)


@router.get(
    "/dependencies",
    response_model=list[dict[str, Any]],
    summary="List metadata dependencies",
)
async def list_metadata_dependencies(
    metadata_object_id: Annotated[UUID, Query(...)],
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    return await service.list_dependencies(db, tenant_id, metadata_object_id)


@router.post(
    "/dependencies/graph",
    response_model=list[dict[str, Any]],
    summary="Get metadata dependencies",
)
async def get_metadata_dependencies(
    payload: dict[str, Any],
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    node_id: str = Query(...),
) -> list[dict[str, Any]]:
    return await service.get_metadata_dependencies(payload, node_id)


@router.post(
    "/dependencies/dependents",
    response_model=list[dict[str, Any]],
    summary="Get metadata dependents",
)
async def get_metadata_dependents(
    payload: dict[str, Any],
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    node_id: str = Query(...),
) -> list[dict[str, Any]]:
    return await service.get_metadata_dependents(payload, node_id)


@router.post(
    "/dependencies/impact",
    response_model=dict[str, Any],
    summary="Analyze metadata impact",
)
async def analyze_metadata_impact(
    payload: dict[str, Any],
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    node_id: str = Query(...),
) -> dict[str, Any]:
    return await service.analyze_metadata_impact(payload, node_id)


@router.post(
    "/dependencies/validate",
    response_model=dict[str, Any],
    summary="Validate metadata changes",
)
async def validate_metadata_changes(
    payload: dict[str, Any],
    current_user: Annotated[User, Depends(require_permission("metadata:write"))],
    node_id: str = Query(...),
) -> dict[str, Any]:
    return await service.validate_metadata_changes(payload, node_id)


@router.get(
    "/objects/{object_id}/layout/active",
    response_model=dict,
    summary="Get active metadata layout schema for an object",
)
async def get_active_metadata_layout_schema(
    object_id: UUID,
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.get_active_layout_schema(db, object_id, tenant_id=tenant_id)


@router.get(
    "/audit-events",
    response_model=MetadataAuditEventListResponse,
    summary="List metadata audit events",
)
async def list_metadata_audit_events(
    current_user: Annotated[User, Depends(require_permission("metadata:read"))],
    tenant_id: Annotated[UUID | None, Depends(get_current_tenant_id)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    metadata_object_id: UUID | None = Query(None),
) -> MetadataAuditEventListResponse:
    events, total = await service.get_audit_events(db, metadata_object_id=metadata_object_id, tenant_id=tenant_id, skip=skip, limit=limit)
    return MetadataAuditEventListResponse(
        items=[MetadataAuditEventResponse.model_validate(event) for event in events],
        total=total,
        skip=skip,
        limit=limit,
    )
