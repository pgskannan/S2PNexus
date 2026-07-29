"""
Suppliers router for S2PNexus.

Handles supplier management operations.
"""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
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
    bulk_upsert_supplier_headers,
    create_supplier,
    delete_all_suppliers,
    delete_supplier,
    find_potential_duplicate_suppliers,
    get_supplier,
    get_supplier_by_external_code,
    get_supplier_hierarchy,
    get_supplier_spend_rollup,
    get_suppliers,
    get_suppliers_count,
    get_suppliers_requalification_due,
    merge_suppliers,
    set_supplier_parent,
    transition_supplier_lifecycle,
    update_supplier,
)
from app.crud.supplier_address import (
    bulk_upsert_supplier_addresses,
    count_supplier_addresses,
    create_supplier_address,
    delete_all_supplier_addresses,
    delete_supplier_address,
    get_supplier_address,
    list_supplier_addresses,
    set_default_supplier_address,
    update_supplier_address,
)
from app.crud.supplier_bank_account import (
    bulk_upsert_supplier_bank_accounts,
    count_supplier_bank_accounts,
    create_supplier_bank_account,
    delete_all_supplier_bank_accounts,
    delete_supplier_bank_account,
    get_supplier_bank_account,
    list_supplier_bank_accounts,
    mask_sensitive_value,
    set_primary_supplier_bank_account,
    update_supplier_bank_account,
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
from app.models.user import User, UserRole
from app.schemas.supplier import (
    SupplierAddressCreate,
    SupplierAddressResponse,
    SupplierAddressUpdate,
    SupplierBankAccountCreate,
    SupplierBankAccountResponse,
    SupplierBankAccountUpdate,
    SupplierCreate,
    SupplierDuplicatesResponse,
    SupplierHierarchyResponse,
    SupplierHierarchyUpdate,
    SupplierLifecycleTransitionRequest,
    SupplierListResponse,
    SupplierMergeRequest,
    SupplierResponse,
    SupplierSpendRollupResponse,
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
from app.services.master_data_import import (
    MasterDataCSVError,
    parse_supplier_addresses_csv,
    parse_supplier_bank_accounts_csv,
    parse_supplier_headers_csv,
)
from app.services.supplier_workflow import (
    apply_supplier_registration_transition_workflow,
    apply_supplier_transition_workflow,
    trigger_supplier_requalification_workflow,
)
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="", tags=["Suppliers"])
settings = get_settings()


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can change supplier master data",
        )


async def _read_csv_text(file: UploadFile) -> str:
    raw = await file.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File is not valid UTF-8 text: {exc}",
        ) from exc


async def _resolve_supplier_id(db: AsyncSession, row: dict) -> UUID | None:
    supplier_id = row.get("supplier_id")
    if supplier_id:
        return UUID(supplier_id)
    external_code = row.get("supplier_external_code")
    if not external_code:
        return None
    supplier = await get_supplier_by_external_code(db, external_code)
    return supplier.id if supplier else None


def _mask_supplier_bank_account_response(account) -> SupplierBankAccountResponse:
    response = SupplierBankAccountResponse.model_validate(account)
    response.account_number = mask_sensitive_value(response.account_number)
    response.iban = mask_sensitive_value(response.iban)
    return response


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


@router.post(
    "/merge",
    response_model=SupplierResponse,
    summary="Merge a duplicate supplier into a surviving golden record",
    description="Reassigns live contracts from the source supplier to the target, marks the source as merged",
)
async def merge_suppliers_endpoint(
    merge_data: SupplierMergeRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierResponse:
    try:
        merged = await merge_suppliers(
            db,
            source_supplier_id=merge_data.source_supplier_id,
            target_supplier_id=merge_data.target_supplier_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SupplierResponse.model_validate(merged)


@router.get("/master-data/headers/count")
async def supplier_headers_count(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    return {"count": await get_suppliers_count(db)}


@router.post("/master-data/headers/upload")
async def upload_supplier_headers(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    _require_admin(current_user)
    csv_text = await _read_csv_text(file)
    try:
        rows = parse_supplier_headers_csv(csv_text)
    except MasterDataCSVError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors}) from exc

    loaded, errors = await bulk_upsert_supplier_headers(
        db,
        [r.__dict__ for r in rows],
        updated_by=current_user.id,
    )
    return {"loaded": loaded, "errors": errors}


@router.delete("/master-data/headers")
async def delete_all_supplier_headers(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    deleted = await delete_all_suppliers(db)
    return {"deleted": deleted}


@router.get("/master-data/addresses/count")
async def supplier_addresses_count(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    return {"count": await count_supplier_addresses(db)}


@router.post("/master-data/addresses/upload")
async def upload_supplier_addresses(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    _require_admin(current_user)
    csv_text = await _read_csv_text(file)
    try:
        rows = parse_supplier_addresses_csv(csv_text)
    except MasterDataCSVError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors}) from exc

    loaded = 0
    errors: list[str] = []
    resolved_rows: list[dict] = []
    for line_num, row in enumerate(rows, start=2):
        supplier_id = None
        if row.supplier_id:
            try:
                supplier_id = UUID(row.supplier_id)
            except ValueError:
                errors.append(f"Row {line_num}: invalid supplier_id")
                continue
        elif row.supplier_external_code:
            supplier = await get_supplier_by_external_code(db, row.supplier_external_code)
            if not supplier:
                errors.append(f"Row {line_num}: supplier_external_code '{row.supplier_external_code}' not found")
                continue
            supplier_id = supplier.id

        if supplier_id is None:
            errors.append(f"Row {line_num}: missing supplier_id or supplier_external_code")
            continue

        resolved_rows.append(
            {
                "supplier_id": supplier_id,
                "address_type": row.address_type,
                "attention_to": row.attention_to,
                "address_line1": row.address_line1,
                "address_line2": row.address_line2,
                "city": row.city,
                "state_province": row.state_province,
                "postal_code": row.postal_code,
                "country": row.country,
                "phone": row.phone,
                "is_default": row.is_default,
            }
        )

    if resolved_rows:
        loaded = await bulk_upsert_supplier_addresses(db, rows=resolved_rows)
    return {"loaded": loaded, "errors": errors}


@router.delete("/master-data/addresses")
async def delete_all_supplier_addresses_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    deleted = await delete_all_supplier_addresses(db)
    return {"deleted": deleted}


@router.get("/master-data/bank-accounts/count")
async def supplier_bank_accounts_count(current_user: Annotated[User, Depends(get_current_active_user)], db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    return {"count": await count_supplier_bank_accounts(db)}


@router.post("/master-data/bank-accounts/upload")
async def upload_supplier_bank_accounts(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    _require_admin(current_user)
    csv_text = await _read_csv_text(file)
    try:
        rows = parse_supplier_bank_accounts_csv(csv_text)
    except MasterDataCSVError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": exc.errors}) from exc

    loaded = 0
    errors: list[str] = []
    resolved_rows: list[dict] = []
    for line_num, row in enumerate(rows, start=2):
        supplier_id = None
        if row.supplier_id:
            try:
                supplier_id = UUID(row.supplier_id)
            except ValueError:
                errors.append(f"Row {line_num}: invalid supplier_id")
                continue
        elif row.supplier_external_code:
            supplier = await get_supplier_by_external_code(db, row.supplier_external_code)
            if not supplier:
                errors.append(f"Row {line_num}: supplier_external_code '{row.supplier_external_code}' not found")
                continue
            supplier_id = supplier.id

        if supplier_id is None:
            errors.append(f"Row {line_num}: missing supplier_id or supplier_external_code")
            continue

        resolved_rows.append(
            {
                "supplier_id": supplier_id,
                "bank_name": row.bank_name,
                "account_holder_name": row.account_holder_name,
                "account_number": row.account_number,
                "iban": row.iban,
                "swift_bic": row.swift_bic,
                "routing_number": row.routing_number,
                "currency": row.currency,
                "is_primary": row.is_primary,
                "intermediary_bank_swift": row.intermediary_bank_swift,
            }
        )

    if resolved_rows:
        loaded = await bulk_upsert_supplier_bank_accounts(db, rows=resolved_rows, updated_by=current_user.id)
    return {"loaded": loaded, "errors": errors}


@router.delete("/master-data/bank-accounts")
async def delete_all_supplier_bank_accounts_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    deleted = await delete_all_supplier_bank_accounts(db)
    return {"deleted": deleted}


# NOTE: The generic "/{supplier_id}" routes below must stay registered *after* every
# other literal-prefixed route on this router (e.g. "/requests", "/registrations",
# "/requalification-due", "/merge"). FastAPI/Starlette match routes in registration
# order using the raw path shape, so a "/{supplier_id}" route declared earlier would
# greedily match those literal paths and fail UUID validation before they ever get a
# chance. Routes shaped "/{supplier_id}/<literal-suffix>" (e.g. hierarchy,
# spend-rollup, duplicates, lifecycle/transition below) don't have this problem since
# their shape never collides with a bare "/{supplier_id}", so they can go anywhere.
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


@router.get(
    "/{supplier_id}/addresses",
    response_model=list[SupplierAddressResponse],
    summary="List supplier addresses",
    description="Get all addresses for a supplier",
)
async def get_supplier_addresses_endpoint(
    supplier_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[SupplierAddressResponse]:
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    addresses = await list_supplier_addresses(db, supplier_id)
    return [SupplierAddressResponse.model_validate(address) for address in addresses]


@router.post(
    "/{supplier_id}/addresses",
    response_model=SupplierAddressResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create supplier address",
    description="Create a new address for a supplier",
)
async def create_supplier_address_endpoint(
    supplier_id: UUID,
    address_data: SupplierAddressCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierAddressResponse:
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    address = await create_supplier_address(db, supplier_id, **address_data.model_dump())
    return SupplierAddressResponse.model_validate(address)


@router.patch(
    "/{supplier_id}/addresses/{address_id}",
    response_model=SupplierAddressResponse,
    summary="Update a supplier address",
    description="Update one of a supplier's addresses",
)
async def update_supplier_address_endpoint(
    supplier_id: UUID,
    address_id: UUID,
    address_update: SupplierAddressUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierAddressResponse:
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    try:
        address = await update_supplier_address(db, supplier_id, address_id, address_update.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SupplierAddressResponse.model_validate(address)


@router.post(
    "/{supplier_id}/addresses/{address_id}/set-default",
    response_model=SupplierAddressResponse,
    summary="Mark a supplier address as default",
    description="Set a supplier address as the default for the supplier",
)
async def set_default_supplier_address_endpoint(
    supplier_id: UUID,
    address_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierAddressResponse:
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    try:
        address = await set_default_supplier_address(db, supplier_id, address_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SupplierAddressResponse.model_validate(address)


@router.delete(
    "/{supplier_id}/addresses/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a supplier address",
    description="Delete a supplier address by ID",
)
async def delete_supplier_address_endpoint(
    supplier_id: UUID,
    address_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    try:
        await delete_supplier_address(db, supplier_id, address_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{supplier_id}/bank-accounts",
    response_model=list[SupplierBankAccountResponse],
    summary="List supplier bank accounts",
    description="Get all bank accounts for a supplier",
)
async def get_supplier_bank_accounts_endpoint(
    supplier_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> list[SupplierBankAccountResponse]:
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    accounts = await list_supplier_bank_accounts(db, supplier_id)
    return [_mask_supplier_bank_account_response(account) for account in accounts]


@router.post(
    "/{supplier_id}/bank-accounts",
    response_model=SupplierBankAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create supplier bank account",
    description="Create a new bank account for a supplier",
)
async def create_supplier_bank_account_endpoint(
    supplier_id: UUID,
    account_data: SupplierBankAccountCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierBankAccountResponse:
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    account = await create_supplier_bank_account(db, supplier_id, updated_by=current_user.id, **account_data.model_dump())
    return _mask_supplier_bank_account_response(account)


@router.patch(
    "/{supplier_id}/bank-accounts/{account_id}",
    response_model=SupplierBankAccountResponse,
    summary="Update a supplier bank account",
    description="Update a supplier bank account by ID",
)
async def update_supplier_bank_account_endpoint(
    supplier_id: UUID,
    account_id: UUID,
    account_update: SupplierBankAccountUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierBankAccountResponse:
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    try:
        account = await update_supplier_bank_account(db, supplier_id, account_id, updated_by=current_user.id, updates=account_update.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _mask_supplier_bank_account_response(account)


@router.post(
    "/{supplier_id}/bank-accounts/{account_id}/set-primary",
    response_model=SupplierBankAccountResponse,
    summary="Set a supplier bank account as primary",
    description="Mark a specific supplier bank account as the primary payment account",
)
async def set_primary_supplier_bank_account_endpoint(
    supplier_id: UUID,
    account_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierBankAccountResponse:
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    try:
        account = await set_primary_supplier_bank_account(db, supplier_id, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _mask_supplier_bank_account_response(account)


@router.delete(
    "/{supplier_id}/bank-accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a supplier bank account",
    description="Delete a supplier bank account by ID",
)
async def delete_supplier_bank_account_endpoint(
    supplier_id: UUID,
    account_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    try:
        await delete_supplier_bank_account(db, supplier_id, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


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


@router.get(
    "/{supplier_id}/hierarchy",
    response_model=SupplierHierarchyResponse,
    summary="Get a supplier's hierarchy context",
    description="Returns the supplier's parent (if any) and direct children",
)
async def get_supplier_hierarchy_endpoint(
    supplier_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierHierarchyResponse:
    try:
        hierarchy = await get_supplier_hierarchy(db, supplier_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return SupplierHierarchyResponse.model_validate(hierarchy)


@router.patch(
    "/{supplier_id}/hierarchy",
    response_model=SupplierResponse,
    summary="Set or clear a supplier's parent in the corporate hierarchy",
    description="Pass parent_supplier_id=null to detach; otherwise parent_supplier_id + relationship_type are both required",
)
async def update_supplier_hierarchy_endpoint(
    supplier_id: UUID,
    hierarchy_update: SupplierHierarchyUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierResponse:
    try:
        supplier = await set_supplier_parent(
            db,
            supplier_id,
            parent_supplier_id=hierarchy_update.parent_supplier_id,
            relationship_type=hierarchy_update.relationship_type,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SupplierResponse.model_validate(supplier)


@router.get(
    "/{supplier_id}/spend-rollup",
    response_model=SupplierSpendRollupResponse,
    summary="Aggregated spend across a supplier and its hierarchy",
    description="Sums invoice spend for the supplier plus every descendant in its hierarchy",
)
async def get_supplier_spend_rollup_endpoint(
    supplier_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierSpendRollupResponse:
    try:
        rollup = await get_supplier_spend_rollup(db, supplier_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return SupplierSpendRollupResponse.model_validate(rollup)


@router.get(
    "/{supplier_id}/duplicates",
    response_model=SupplierDuplicatesResponse,
    summary="Find potential duplicate suppliers",
    description="Multi-factor duplicate detection: exact tax ID / website domain match plus fuzzy name similarity",
)
async def get_supplier_duplicates_endpoint(
    supplier_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    min_score: float = Query(0.5, ge=0.0, le=1.0, description="Minimum combined match score to include a candidate"),
    limit: int = Query(10, ge=1, le=100),
) -> SupplierDuplicatesResponse:
    try:
        scored = await find_potential_duplicate_suppliers(db, supplier_id, min_score=min_score, limit=limit)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return SupplierDuplicatesResponse(
        supplier_id=supplier_id,
        candidates=[
            {"supplier_id": candidate.id, "name": candidate.name, "match_score": score, "match_reasons": reasons}
            for candidate, score, reasons in scored
        ],
    )


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