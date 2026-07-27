"""
Suppliers router for S2PNexus.

Handles supplier management operations.
"""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.supplier import (
    CreateSupplierRegistrationCommand,
    CreateSupplierRegistrationCommandHandler,
    CreateSupplierRequestCommand,
    CreateSupplierRequestCommandHandler,
    TransitionSupplierRegistrationCommand,
    TransitionSupplierRegistrationCommandHandler,
    TransitionSupplierRequestCommand,
    TransitionSupplierRequestCommandHandler,
)
from app.core.config import get_settings
from app.crud.supplier import (
    create_supplier,
    delete_supplier,
    get_supplier,
    get_suppliers,
    get_suppliers_count,
    get_suppliers_requalification_due,
    transition_supplier_lifecycle,
    update_supplier,
)
from app.crud.supplier_registration import (
    convert_registration_to_supplier,
    create_supplier_registration,
    get_supplier_registration,
    get_supplier_registrations,
    get_supplier_registrations_count,
    transition_supplier_registration,
    update_supplier_registration,
)
from app.crud.supplier_request import (
    create_supplier_request,
    get_supplier_request,
    get_supplier_requests,
    get_supplier_requests_count,
    transition_supplier_request,
    update_supplier_request,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.supplier import (
    SupplierCreate,
    SupplierLifecycleTransitionRequest,
    SupplierListResponse,
    SupplierResponse,
    SupplierUpdate,
)
from app.schemas.supplier_registration import (
    SupplierRegistrationCreate,
    SupplierRegistrationListResponse,
    SupplierRegistrationResponse,
    SupplierRegistrationUpdate,
)
from app.schemas.supplier_request import (
    SupplierRequestCreate,
    SupplierRequestListResponse,
    SupplierRequestResponse,
    SupplierRequestUpdate,
)
from app.services.supplier_workflow import (
    apply_supplier_registration_transition_workflow,
    apply_supplier_transition_workflow,
    trigger_supplier_requalification_workflow,
)
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="", tags=["Suppliers"])
settings = get_settings()


@router.get(
    "",
    response_model=SupplierListResponse,
    summary="List suppliers",
    description="Get paginated list of suppliers",
)
async def list_suppliers(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    search: str | None = Query(None, description="Search term for name/email"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    sort_by: str = Query("name", description="Sort field"),
    sort_order: str = Query("asc", description="Sort direction (asc/desc)"),
) -> SupplierListResponse:
    """
    List all suppliers with pagination and search.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records
        search: Search term
        is_active: Filter by active status
        current_user: Current authenticated user
        db: Database session

    Returns:
        SupplierListResponse: Paginated supplier list
    """
    suppliers = await get_suppliers(
        db,
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = await get_suppliers_count(db, search=search, is_active=is_active)

    return SupplierListResponse(
        items=[SupplierResponse.model_validate(supplier) for supplier in suppliers],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create supplier",
    description="Create a new supplier",
)
async def create_supplier_endpoint(
    supplier_data: SupplierCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierResponse:
    """
    Create a new supplier.

    Args:
        supplier_data: Supplier creation data
        current_user: Current authenticated user
        db: Database session

    Returns:
        SupplierResponse: Created supplier
    """
    supplier = await create_supplier(db, supplier_data, created_by=current_user.id)
    return SupplierResponse.model_validate(supplier)


@router.get("/requests", response_model=SupplierRequestListResponse, summary="List supplier requests")
async def list_supplier_requests(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str | None = Query(None),
    status: str | None = Query(None),
) -> SupplierRequestListResponse:
    supplier_requests = await get_supplier_requests(db, skip=skip, limit=limit, search=search, status=status, tenant_id=current_user.tenant_id)
    total = await get_supplier_requests_count(db, search=search, status=status, tenant_id=current_user.tenant_id)
    return SupplierRequestListResponse(items=[SupplierRequestResponse.model_validate(item) for item in supplier_requests], total=total, skip=skip, limit=limit)


@router.post("/requests", response_model=SupplierRequestResponse, status_code=status.HTTP_201_CREATED, summary="Create supplier request")
async def create_supplier_request_endpoint(
    request_data: SupplierRequestCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierRequestResponse:
    handler = CreateSupplierRequestCommandHandler(create_supplier_request_service=create_supplier_request)
    command = CreateSupplierRequestCommand(supplier_request_data=request_data.model_dump(), tenant_id=current_user.tenant_id)
    supplier_request = await handler.handle(command, db=db)

    response_payload = {
        **supplier_request.__dict__,
        "created_at": getattr(supplier_request, "created_at", datetime.now(timezone.utc)),
        "updated_at": getattr(supplier_request, "updated_at", datetime.now(timezone.utc)),
    }
    return SupplierRequestResponse.model_validate(response_payload)


@router.get("/requests/{supplier_request_id}", response_model=SupplierRequestResponse, summary="Get supplier request")
async def get_supplier_request_endpoint(
    supplier_request_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierRequestResponse:
    supplier_request = await get_supplier_request(db, supplier_request_id, tenant_id=current_user.tenant_id)
    if not supplier_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier request not found")

    response_payload = {
        **supplier_request.__dict__,
        "created_at": getattr(supplier_request, "created_at", datetime.now(timezone.utc)),
        "updated_at": getattr(supplier_request, "updated_at", datetime.now(timezone.utc)),
    }
    return SupplierRequestResponse.model_validate(response_payload)


@router.patch("/requests/{supplier_request_id}", response_model=SupplierRequestResponse, summary="Update supplier request")
async def update_supplier_request_endpoint(
    supplier_request_id: UUID,
    request_update: SupplierRequestUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierRequestResponse:
    supplier_request = await update_supplier_request(db, supplier_request_id, request_update, tenant_id=current_user.tenant_id)
    if not supplier_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier request not found")

    response_payload = {
        **supplier_request.__dict__,
        "created_at": getattr(supplier_request, "created_at", datetime.now(timezone.utc)),
        "updated_at": getattr(supplier_request, "updated_at", datetime.now(timezone.utc)),
    }
    return SupplierRequestResponse.model_validate(response_payload)


@router.post("/requests/{supplier_request_id}/transition", response_model=SupplierRequestResponse, summary="Transition supplier request")
async def transition_supplier_request_endpoint(
    request: Request,
    supplier_request_id: UUID,
    transition_data: dict[str, str | dict | None],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierRequestResponse:
    supplier_request = await get_supplier_request(db, supplier_request_id, tenant_id=current_user.tenant_id)
    if not supplier_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier request not found")

    action = str(transition_data.get("action", "submit"))
    handler = TransitionSupplierRequestCommandHandler(transition_supplier_request_service=transition_supplier_request)
    transitioned_request = await handler.handle(
        TransitionSupplierRequestCommand(
            supplier_request_id=str(supplier_request_id),
            action=action,
            details={"details": transition_data.get("details")},
            tenant_id=current_user.tenant_id,
        ),
        db=db,
        actor_id=current_user.id,
    )
    if not transitioned_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier request not found")

    event_type = {
        "submit": "SupplierRequestSubmitted",
        "approve": "SupplierRequestApproved",
        "reject": "SupplierRequestRejected",
        "cancel": "SupplierRequestCancelled",
    }.get(action.lower(), "SupplierRequestSubmitted")
    await apply_supplier_transition_workflow(
        transitioned_request,
        event_type,
        payload={"request_id": str(transitioned_request.id), "action": action},
        state=transitioned_request,
        event_bus=getattr(request.app.state, "event_bus", None),
        actor_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )

    response_payload = {
        **transitioned_request.__dict__,
        "created_at": getattr(transitioned_request, "created_at", datetime.now(timezone.utc)),
        "updated_at": getattr(transitioned_request, "updated_at", datetime.now(timezone.utc)),
    }
    return SupplierRequestResponse.model_validate(response_payload)


@router.get("/registrations", response_model=SupplierRegistrationListResponse, summary="List supplier registrations")
async def list_supplier_registrations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str | None = Query(None),
    status: str | None = Query(None),
) -> SupplierRegistrationListResponse:
    registrations = await get_supplier_registrations(db, skip=skip, limit=limit, search=search, status=status, tenant_id=current_user.tenant_id)
    total = await get_supplier_registrations_count(db, search=search, status=status, tenant_id=current_user.tenant_id)
    return SupplierRegistrationListResponse(
        items=[SupplierRegistrationResponse.model_validate(item) for item in registrations],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/registrations",
    response_model=SupplierRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create supplier registration",
)
async def create_supplier_registration_endpoint(
    registration_data: SupplierRegistrationCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierRegistrationResponse:
    handler = CreateSupplierRegistrationCommandHandler(
        create_supplier_registration_service=create_supplier_registration
    )
    command = CreateSupplierRegistrationCommand(supplier_registration_data=registration_data.model_dump(), tenant_id=current_user.tenant_id)
    registration = await handler.handle(command, db=db)
    return SupplierRegistrationResponse.model_validate(registration)


@router.get("/registrations/{registration_id}", response_model=SupplierRegistrationResponse, summary="Get supplier registration")
async def get_supplier_registration_endpoint(
    registration_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierRegistrationResponse:
    registration = await get_supplier_registration(db, registration_id, tenant_id=current_user.tenant_id)
    if not registration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier registration not found")
    return SupplierRegistrationResponse.model_validate(registration)


@router.patch("/registrations/{registration_id}", response_model=SupplierRegistrationResponse, summary="Update supplier registration")
async def update_supplier_registration_endpoint(
    registration_id: UUID,
    registration_update: SupplierRegistrationUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierRegistrationResponse:
    registration = await update_supplier_registration(db, registration_id, registration_update, tenant_id=current_user.tenant_id)
    if not registration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier registration not found")
    return SupplierRegistrationResponse.model_validate(registration)


@router.post(
    "/registrations/{registration_id}/transition",
    response_model=SupplierRegistrationResponse,
    summary="Transition supplier registration",
)
async def transition_supplier_registration_endpoint(
    request: Request,
    registration_id: UUID,
    transition_data: dict[str, str | dict | None],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierRegistrationResponse:
    existing = await get_supplier_registration(db, registration_id, tenant_id=current_user.tenant_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier registration not found")

    action = str(transition_data.get("action", "submit"))
    handler = TransitionSupplierRegistrationCommandHandler(
        transition_supplier_registration_service=transition_supplier_registration
    )
    transitioned = await handler.handle(
        TransitionSupplierRegistrationCommand(
            supplier_registration_id=str(registration_id),
            action=action,
            details={"details": transition_data.get("details")},
            tenant_id=current_user.tenant_id,
        ),
        db=db,
        actor_id=current_user.id,
    )
    if not transitioned:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier registration not found")

    event_type = {
        "submit": "SupplierRegistrationSubmitted",
        "review": "SupplierRegistrationUnderReview",
        "approve": "SupplierRegistrationApproved",
        "reject": "SupplierRegistrationRejected",
        "cancel": "SupplierRegistrationCancelled",
    }.get(action.lower(), "SupplierRegistrationSubmitted")

    decision = await apply_supplier_registration_transition_workflow(
        transitioned,
        event_type,
        payload={"registration_id": str(transitioned.id), "action": action},
        state=transitioned,
        event_bus=getattr(request.app.state, "event_bus", None),
        actor_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )

    # Auto-approve low-risk registrations at submission time.
    if action.lower() == "submit" and not decision["requires_approval"]:
        transitioned = await transition_supplier_registration(
            db, registration_id, actor_id=current_user.id, action="approve", tenant_id=current_user.tenant_id
        )

    return SupplierRegistrationResponse.model_validate(transitioned)


@router.post(
    "/registrations/{registration_id}/convert",
    response_model=SupplierRegistrationResponse,
    summary="Convert an approved supplier registration into an active supplier",
)
async def convert_supplier_registration_endpoint(
    registration_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierRegistrationResponse:
    existing = await get_supplier_registration(db, registration_id, tenant_id=current_user.tenant_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier registration not found")

    try:
        registration = await convert_registration_to_supplier(db, registration_id, actor_id=current_user.id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SupplierRegistrationResponse.model_validate(registration)


@router.get(
    "/requalification-due",
    response_model=list[SupplierResponse],
    summary="List suppliers due for requalification",
    description="Suppliers whose next_requalification_due_at has passed and aren't already mid-requalification or offboarding",
)
async def list_suppliers_requalification_due(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[SupplierResponse]:
    suppliers = await get_suppliers_requalification_due(db)
    return [SupplierResponse.model_validate(supplier) for supplier in suppliers]


# NOTE: The generic "/{supplier_id}" routes below must stay registered *after* every
# other literal-prefixed route on this router (e.g. "/requests", "/registrations",
# "/requalification-due"). FastAPI/Starlette match routes in registration order using
# the raw path shape, so a "/{supplier_id}" route declared earlier would greedily
# match those literal paths and fail UUID validation before they ever get a chance.
@router.get(
    "/{supplier_id}",
    response_model=SupplierResponse,
    summary="Get supplier by ID",
    description="Get supplier details by ID",
)
async def get_supplier_by_id(
    supplier_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierResponse:
    """
    Get supplier by ID.

    Args:
        supplier_id: Supplier UUID
        current_user: Current authenticated user
        db: Database session

    Returns:
        SupplierResponse: Supplier details

    Raises:
        HTTPException: If supplier not found
    """
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )
    return SupplierResponse.model_validate(supplier)


@router.patch(
    "/{supplier_id}",
    response_model=SupplierResponse,
    summary="Update supplier",
    description="Update supplier details",
)
async def update_supplier_by_id(
    supplier_id: UUID,
    supplier_update: SupplierUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierResponse:
    """
    Update supplier by ID.

    Args:
        supplier_id: Supplier UUID
        supplier_update: Supplier update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        SupplierResponse: Updated supplier details

    Raises:
        HTTPException: If supplier not found
    """
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    updated_supplier = await update_supplier(db, supplier_id, supplier_update)
    return SupplierResponse.model_validate(updated_supplier)


@router.post(
    "/{supplier_id}/lifecycle/transition",
    response_model=SupplierResponse,
    summary="Transition supplier lifecycle state",
    description="Move a supplier through continuous monitoring, requalification, and offboarding states",
)
async def transition_supplier_lifecycle_endpoint(
    supplier_id: UUID,
    transition_data: SupplierLifecycleTransitionRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierResponse:
    try:
        supplier = await transition_supplier_lifecycle(
            db,
            supplier_id,
            action=transition_data.action,
            reason=transition_data.reason,
            next_requalification_due_at=transition_data.next_requalification_due_at,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Starting requalification also kicks off the generic workflow engine, if an
    # operator has configured a WorkflowDefinition for entity_type='supplier'.
    # Best-effort: no configured definition yet is expected, not an error.
    if transition_data.action.lower() == "start_requalification":
        await trigger_supplier_requalification_workflow(db, supplier, started_by=current_user.id)

    return SupplierResponse.model_validate(supplier)


@router.delete(
    "/{supplier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete supplier",
    description="Delete supplier by ID",
)
async def delete_supplier_by_id(
    supplier_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete supplier by ID.

    Args:
        supplier_id: Supplier UUID
        current_user: Current authenticated user
        db: Database session

    Raises:
        HTTPException: If supplier not found
    """
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    await delete_supplier(db, supplier_id)