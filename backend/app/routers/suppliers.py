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
from sqlalchemy import select

from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.services.preferred_supplier import recompute_preferred_status
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
    PreferredOverrideRequest,
    PreferredOverrideResponse,
    PreferredSupplierListResponse,
    PreferredSupplierStatusResponse,
    SupplierMergeRequest,
    SupplierQualificationResponse,
    SupplierQualificationUpsert,
    SupplierResponse,
    SupplierSpendRollupResponse,
    SupplierUpdate,
)
from app.crud.supplier_qualification import (
    get_supplier_qualification,
    upsert_supplier_qualification,
)
from app.schemas.supplier_registration import (
    RegistrationImportResultOut,
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
from app.crud.template import TemplateValidationError, get_response_for_entity, upsert_template_response
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="", tags=["Suppliers"])
settings = get_settings()

# Template answer keys that mirror legacy SupplierRequest columns one-for-one
# (question_key == column name by construction, see
# scripts/seed_supplier_request_template.py). yes_no answers arrive as
# "yes"/"no" strings; booleans/Decimals are coerced for the fixed columns.
_LEGACY_ANSWER_KEYS = (
    "business_justification",
    "commodity_categories",
    "suggested_supplier_name",
    "existing_supplier_check",
    "preferred_region",
    "estimated_annual_spend",
    "diversity_required",
    "risk_justification",
)
_LEGACY_BOOL_KEYS = {"existing_supplier_check", "diversity_required"}


def _legacy_fields_from_answers(answers: dict) -> dict:
    """Mirror known template answers onto the legacy fixed columns."""
    from decimal import Decimal, InvalidOperation

    fields: dict = {}
    for key in _LEGACY_ANSWER_KEYS:
        if key not in answers or answers[key] is None:
            continue
        value = answers[key]
        if key in _LEGACY_BOOL_KEYS:
            fields[key] = value is True or str(value).strip().lower() in {"yes", "true", "1"}
        elif key == "estimated_annual_spend":
            try:
                fields[key] = Decimal(str(value))
            except (InvalidOperation, ValueError):
                continue  # unparseable spend stays template-only
        else:
            fields[key] = str(value)
    return fields


def _answers_from_legacy_fields(legacy_data: dict) -> dict:
    """Mirror legacy fixed-column values into template answers ("yes"/"no"
    strings for booleans, stringified Decimal for spend -- same encoding as
    the backfill script)."""
    answers: dict = {}
    for key in _LEGACY_ANSWER_KEYS:
        value = legacy_data.get(key)
        if value is None:
            continue
        if key in _LEGACY_BOOL_KEYS:
            answers[key] = "yes" if value else "no"
        elif key == "estimated_annual_spend":
            answers[key] = str(value)
        else:
            answers[key] = value
    return answers


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
    # Template Framework Phase 1: `answers` is the dynamic-questionnaire
    # payload, not a SupplierRequest column -- split it off before the legacy
    # create path, and mirror known legacy keys from answers into the fixed
    # columns so both representations stay consistent regardless of whether
    # the client sent legacy fields, answers, or both (answers win).
    answers = request_data.answers or {}
    legacy_data = request_data.model_dump(exclude={"answers"})
    legacy_data.update(_legacy_fields_from_answers(answers))

    handler = CreateSupplierRequestCommandHandler(create_supplier_request_service=create_supplier_request)
    command = CreateSupplierRequestCommand(supplier_request_data=legacy_data, tenant_id=current_user.tenant_id)
    supplier_request = await handler.handle(command, db=db)

    # Persist the full answer set (legacy-mirrored + template-only keys) as
    # the request's TemplateResponse. Returns None when no supplier_request
    # template is published -- legacy behavior unchanged in that case.
    # submit=False on purpose: creation produces a draft, and drafts may have
    # gaps. Mandatory-answer validation + scoring run at the submit
    # transition (see transition_supplier_request), matching when the spec's
    # conditional-mandatory rules are actually enforceable.
    template_response = await upsert_template_response(
        db,
        module="supplier_request",
        entity_type="supplier_request",
        entity_id=supplier_request.id,
        answers={**_answers_from_legacy_fields(legacy_data), **answers},
        submitted_by=current_user.id,
        tenant_id=current_user.tenant_id,
        submit=False,
    )

    response_payload = {
        **supplier_request.__dict__,
        "created_at": getattr(supplier_request, "created_at", datetime.now(timezone.utc)),
        "updated_at": getattr(supplier_request, "updated_at", datetime.now(timezone.utc)),
        "template_response": template_response,
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

    template_response = await get_response_for_entity(
        db, "supplier_request", supplier_request.id, tenant_id=current_user.tenant_id
    )
    response_payload = {
        **supplier_request.__dict__,
        "created_at": getattr(supplier_request, "created_at", datetime.now(timezone.utc)),
        "updated_at": getattr(supplier_request, "updated_at", datetime.now(timezone.utc)),
        "template_response": template_response,
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
    try:
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
    except TemplateValidationError as exc:
        # Submit with unanswered mandatory template questions: request stays
        # in draft, client gets the exact missing question keys.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Missing mandatory template answers", "missing": exc.missing_keys},
        ) from exc
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


@router.post(
    "/registrations/{registration_id}/send",
    response_model=SupplierRegistrationResponse,
    summary="Send (or re-send) the Excel registration workbook (MANUAL mode / SLP Admin)",
)
async def send_registration_workbook_endpoint(
    registration_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierRegistrationResponse:
    # FS Section 3: Creator or SLP Admin (administrator / supplier_manager) can trigger MANUAL send.
    registration = await get_supplier_registration(db, registration_id, tenant_id=current_user.tenant_id)
    if not registration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier registration not found")
    is_creator = registration.submitted_by == current_user.id
    is_slp = current_user.role in (UserRole.ADMINISTRATOR, UserRole.SUPPLIER_MANAGER) or current_user.is_superuser
    if not (is_creator or is_slp):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Creator or SLP Admin can send registration")
    from app.services.registration_trigger import send_registration_workbook

    updated = await send_registration_workbook(db, registration_id, actor_id=current_user.id, commit=True)
    return SupplierRegistrationResponse.model_validate(updated)


@router.get(
    "/registrations/{registration_id}/workbook",
    summary="Download the sent registration workbook",
    response_model=None,
)
async def download_registration_workbook_endpoint(
    registration_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    from app.services import file_storage

    registration = await get_supplier_registration(db, registration_id, tenant_id=current_user.tenant_id)
    if not registration or not registration.sent_workbook_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workbook not found")
    try:
        data = file_storage.load_bytes(registration.sent_workbook_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workbook file missing on disk") from exc
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{registration.registration_number}.xlsx"'},
    )


@router.post(
    "/registrations/{registration_id}/import",
    response_model=RegistrationImportResultOut,
    summary="Import a completed registration workbook (SLP Admin)",
)
async def import_registration_workbook_endpoint(
    registration_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
) -> RegistrationImportResultOut:
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        # SLP Admin maps to administrator (and supplier_manager as practical stand-in)
        if current_user.role != UserRole.SUPPLIER_MANAGER:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only SLP Admin can import workbooks")

    from sqlalchemy import select

    from app.models.supplier_type import SupplierType
    from app.schemas.supplier_registration import RegistrationImportFailureOut, RegistrationImportResultOut
    from app.services import file_storage
    from app.services.excel_registration import (
        SHEET_INSTRUCTIONS,
        SHEET_SUPPLIER_INFO,
        _module_sheet_name,
        parse_and_validate_workbook,
    )
    from app.services.registration_trigger import apply_import_result, _resolve_templates
    from dataclasses import asdict

    registration = await get_supplier_registration(db, registration_id, tenant_id=current_user.tenant_id)
    if not registration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier registration not found")
    if not registration.structure_hash:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Registration workbook has not been sent yet")

    supplier_type = None
    if registration.supplier_type_id:
        supplier_type = (
            await db.execute(select(SupplierType).where(SupplierType.id == registration.supplier_type_id))
        ).scalar_one_or_none()
    module_codes = list(supplier_type.required_questionnaire_modules or []) if supplier_type else []
    templates = await _resolve_templates(db, module_codes, registration.tenant_id)
    # Preserve the send-time sheet order: Instructions, Supplier Information, then
    # modules in the type's required_questionnaire_modules order (same as generate).
    expected_sheets = [SHEET_INSTRUCTIONS, SHEET_SUPPLIER_INFO] + [
        _module_sheet_name(c) for c in module_codes if c in templates
    ]
    raw = await file.read()

    result = parse_and_validate_workbook(
        raw,
        registration,
        expected_hash=registration.structure_hash,
        expected_template_version=registration.template_version or "1.0",
        expected_questionnaire_version=registration.questionnaire_version or "1.0",
        expected_sheets=expected_sheets,
        templates_by_module_code=templates,
    )

    returned_key = file_storage.build_key(registration.id, "returned")
    file_storage.save_bytes(returned_key, raw)

    if not result.ok:
        if result.error_report_bytes:
            err_key = file_storage.build_key(registration.id, "error_report")
            file_storage.save_bytes(err_key, result.error_report_bytes)
        if result.import_summary_text:
            file_storage.save_bytes(
                file_storage.build_key(registration.id, "import_summary"),
                result.import_summary_text.encode("utf-8"),
            )
        return RegistrationImportResultOut(
            ok=False,
            failures=[RegistrationImportFailureOut(**asdict(f)) for f in result.failures],
            registration=SupplierRegistrationResponse.model_validate(registration),
            import_summary=result.import_summary_text,
            error_report_available=bool(result.error_report_bytes),
        )

    updated = await apply_import_result(
        db, registration, result, actor_id=current_user.id, returned_path=returned_key, commit=True
    )
    return RegistrationImportResultOut(
        ok=True,
        failures=[],
        registration=SupplierRegistrationResponse.model_validate(updated),
        import_summary=result.import_summary_text,
        error_report_available=False,
    )


@router.get(
    "/registrations/{registration_id}/error-report",
    summary="Download ErrorReport.xlsx from the last failed import",
    response_model=None,
)
async def download_registration_error_report_endpoint(
    registration_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    from app.services import file_storage

    registration = await get_supplier_registration(db, registration_id, tenant_id=current_user.tenant_id)
    if not registration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier registration not found")
    key = file_storage.build_key(registration.id, "error_report")
    try:
        data = file_storage.load_bytes(key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No error report available") from exc
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="ErrorReport.xlsx"'},
    )


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


# --- Preferred Supplier Framework (Template Framework Phase 3) --------------
# NOTE: "/preferred-statuses" and "/preferred/recompute-all" are literal paths
# and MUST stay registered before the generic "/{supplier_id}" routes below
# (see the routing-order note further down).


@router.get(
    "/preferred-statuses",
    response_model=PreferredSupplierListResponse,
    summary="List preferred supplier statuses",
)
async def list_preferred_statuses_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = Query(None),
    region: str | None = Query(None),
) -> PreferredSupplierListResponse:
    from app.models.preferred_supplier import PreferredSupplierStatus

    query = select(PreferredSupplierStatus)
    if current_user.tenant_id is not None:
        query = query.where(
            (PreferredSupplierStatus.tenant_id == current_user.tenant_id)
            | (PreferredSupplierStatus.tenant_id.is_(None))
        )
    if status_filter:
        query = query.where(PreferredSupplierStatus.preferred_status == status_filter)
    if category:
        query = query.where(PreferredSupplierStatus.category == category)
    if region:
        query = query.where(PreferredSupplierStatus.region == region)
    rows = (await db.execute(query.order_by(PreferredSupplierStatus.composite_score.desc().nullslast()))).scalars().all()
    return PreferredSupplierListResponse(
        items=[PreferredSupplierStatusResponse.model_validate(row) for row in rows],
        total=len(rows),
    )


@router.post(
    "/preferred/recompute-all",
    response_model=PreferredSupplierListResponse,
    summary="Recompute preferred status for all suppliers (admin)",
)
async def recompute_all_preferred_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> PreferredSupplierListResponse:
    _require_admin(current_user)
    supplier_ids = (await db.execute(select(Supplier.id).where(Supplier.is_active.is_(True)))).scalars().all()
    rows = []
    for sid in supplier_ids:
        rows.append(
            await recompute_preferred_status(db, sid, tenant_id=current_user.tenant_id, commit=False)
        )
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return PreferredSupplierListResponse(
        items=[PreferredSupplierStatusResponse.model_validate(row) for row in rows],
        total=len(rows),
    )


@router.get(
    "/{supplier_id}/preferred",
    response_model=PreferredSupplierStatusResponse,
    summary="Get a supplier's preferred status",
)
async def get_preferred_status_endpoint(
    supplier_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> PreferredSupplierStatusResponse:
    from app.models.preferred_supplier import PreferredSupplierStatus

    row = (
        await db.execute(
            select(PreferredSupplierStatus).where(PreferredSupplierStatus.supplier_id == supplier_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No preferred status computed for this supplier yet -- POST .../preferred/recompute first",
        )
    return PreferredSupplierStatusResponse.model_validate(row)


@router.post(
    "/{supplier_id}/preferred/recompute",
    response_model=PreferredSupplierStatusResponse,
    summary="Recompute a supplier's preferred status (admin/category manager)",
)
async def recompute_preferred_endpoint(
    supplier_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> PreferredSupplierStatusResponse:
    if current_user.role not in (UserRole.ADMINISTRATOR, UserRole.CATEGORY_MANAGER) and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and category managers can recompute preferred status",
        )
    try:
        row = await recompute_preferred_status(db, supplier_id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PreferredSupplierStatusResponse.model_validate(row)


@router.patch(
    "/{supplier_id}/preferred/override",
    response_model=PreferredOverrideResponse,
    summary="Manually override a supplier's preferred status (admin, routed through review workflow when configured)",
)
async def override_preferred_status_endpoint(
    supplier_id: UUID,
    payload: PreferredOverrideRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> PreferredOverrideResponse:
    """Template Framework Phase 4: manual overrides route through the
    preferred_supplier_review workflow (Category Manager -> Procurement Head
    -> Risk Team -> Compliance) when one is configured; the override applies
    only when every reviewer approves. With no definition configured, the
    override applies immediately (fallback contract). Auto-classification
    (recompute) never routes here -- spec allows it to bypass review."""
    from app.models.preferred_supplier import PreferredSupplierStatus
    from app.services.preferred_supplier import (
        apply_preferred_override,
        start_preferred_override_workflow,
    )

    _require_admin(current_user)
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")

    try:
        instance = await start_preferred_override_workflow(
            db,
            supplier_id,
            target_status=payload.status,
            reason=payload.reason,
            actor_id=current_user.id,
            tenant_id=current_user.tenant_id,
        )
        if instance is None:
            row = await apply_preferred_override(
                db,
                supplier_id=supplier_id,
                target_status=payload.status,
                reason=payload.reason,
                actor_id=current_user.id,
                tenant_id=current_user.tenant_id,
            )
            return PreferredOverrideResponse(
                applied=True,
                review_instance_id=None,
                status=PreferredSupplierStatusResponse.model_validate(row),
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # Workflow started: the override is pending review. Re-fetch the current
    # row (start_workflow_instance commits, expiring loaded objects).
    row = (
        await db.execute(
            select(PreferredSupplierStatus).where(PreferredSupplierStatus.supplier_id == supplier_id)
        )
    ).scalar_one_or_none()
    if row is None:
        # Override requested before any recompute: create the baseline row so
        # the response (and the review's eventual completion) has a target.
        from app.services.preferred_supplier import recompute_preferred_status

        row = await recompute_preferred_status(db, supplier_id, tenant_id=current_user.tenant_id)
    return PreferredOverrideResponse(
        applied=False,
        review_instance_id=instance.id,
        status=PreferredSupplierStatusResponse.model_validate(row),
    )


# --- Supplier Qualification (placeholder, Template Framework Phase 2) -------


@router.get(
    "/{supplier_id}/qualification",
    response_model=SupplierQualificationResponse,
    summary="Get supplier qualification (placeholder record)",
)
async def get_supplier_qualification_endpoint(
    supplier_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierQualificationResponse:
    qualification = await get_supplier_qualification(db, supplier_id, tenant_id=current_user.tenant_id)
    if not qualification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No qualification record for this supplier")
    return SupplierQualificationResponse.model_validate(qualification)


@router.put(
    "/{supplier_id}/qualification",
    response_model=SupplierQualificationResponse,
    summary="Set supplier qualification (admin/category manager)",
)
async def upsert_supplier_qualification_endpoint(
    supplier_id: UUID,
    payload: SupplierQualificationUpsert,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> SupplierQualificationResponse:
    """Manual qualification entry -- the placeholder stand-in for the future
    template-driven qualification module (see models/supplier_qualification.py).
    Grade is derived server-side from score via the spec Section 7 bands."""
    if current_user.role not in (UserRole.ADMINISTRATOR, UserRole.CATEGORY_MANAGER) and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators and category managers can set supplier qualifications",
        )
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    try:
        qualification = await upsert_supplier_qualification(
            db, supplier_id, payload, actor_id=current_user.id, tenant_id=current_user.tenant_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return SupplierQualificationResponse.model_validate(qualification)


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