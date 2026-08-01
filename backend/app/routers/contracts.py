"""
Contracts router for S2PNexus.

Handles contract management operations.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crud.contract import (
    create_contract,
    delete_contract,
    get_contract,
    get_contracts,
    get_contracts_count,
    transition_contract,
    update_contract,
)
from app.crud.contract_lifecycle import (
    add_obligation,
    create_clause,
    create_template,
    get_clause,
    get_clauses,
    get_clauses_count,
    get_template,
    get_templates,
    get_templates_count,
    link_clause_to_contract,
    renew_contract,
    update_clause,
    update_obligation,
    update_template,
)
from app.database.session import get_db
from app.models.contract import Contract
from app.models.user import User
from app.schemas.contract import ContractResponse, ContractCreate, ContractUpdate, ContractListResponse
from app.schemas.contract_lifecycle import (
    ContractClauseCreate,
    ContractClauseListResponse,
    ContractClauseLinkCreate,
    ContractClauseLinkResponse,
    ContractClauseResponse,
    ContractClauseUpdate,
    ContractObligationCreate,
    ContractObligationResponse,
    ContractObligationUpdate,
    ContractRenewalCreate,
    ContractTemplateCreate,
    ContractTemplateListResponse,
    ContractTemplateResponse,
    ContractTemplateUpdate,
)
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/contracts", tags=["Contracts"])
settings = get_settings()


@router.get(
    "",
    response_model=ContractListResponse,
    summary="List contracts",
    description="Get paginated list of contracts",
)
async def list_contracts(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    search: str | None = Query(None, description="Search term"),
    status: str | None = Query(None, description="Filter by status"),
    supplier_id: UUID | None = Query(None, description="Filter by supplier"),
    sort_by: str = Query("title", description="Sort field"),
    sort_order: str = Query("asc", description="Sort direction (asc/desc)"),
) -> ContractListResponse:
    """
    List all contracts with pagination and filters.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records
        search: Search term
        status: Filter by status
        current_user: Current authenticated user
        db: Database session

    Returns:
        ContractListResponse: Paginated contract list
    """
    contracts = await get_contracts(
        db,
        skip=skip,
        limit=limit,
        search=search,
        status=status,
        supplier_id=supplier_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = await get_contracts_count(db, search=search, status=status, supplier_id=supplier_id)

    return ContractListResponse(
        items=[ContractResponse.model_validate(contract) for contract in contracts],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "",
    response_model=ContractResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create contract",
    description="Create a new contract",
)
async def create_contract_endpoint(
    contract_data: ContractCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractResponse:
    """
    Create a new contract.

    Args:
        contract_data: Contract creation data
        current_user: Current authenticated user
        db: Database session

    Returns:
        ContractResponse: Created contract
    """
    contract = await create_contract(db, contract_data, created_by=current_user.id)
    return ContractResponse.model_validate(contract)


# NOTE: These literal-prefixed routes ("/clauses", "/templates") must stay registered
# *before* the generic "/{contract_id}" routes below. FastAPI/Starlette match routes
# in registration order using the raw path shape, so a "/{contract_id}" route
# declared earlier would greedily match "/clauses" or "/templates" and fail UUID
# validation before those routes ever get a chance (see the equivalent fix applied
# to routers/suppliers.py).
@router.get("/clauses", response_model=ContractClauseListResponse, summary="List clause library entries")
async def list_clauses(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str | None = Query(None),
    category: str | None = Query(None),
) -> ContractClauseListResponse:
    clauses = await get_clauses(db, skip=skip, limit=limit, search=search, category=category)
    total = await get_clauses_count(db, search=search, category=category)
    return ContractClauseListResponse(
        items=[ContractClauseResponse.model_validate(c) for c in clauses], total=total, skip=skip, limit=limit
    )


@router.post(
    "/clauses",
    response_model=ContractClauseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a clause to the clause library",
)
async def create_clause_endpoint(
    clause_data: ContractClauseCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractClauseResponse:
    clause = await create_clause(db, clause_data, created_by=current_user.id)
    return ContractClauseResponse.model_validate(clause)


@router.get("/clauses/{clause_id}", response_model=ContractClauseResponse, summary="Get a clause library entry")
async def get_clause_endpoint(
    clause_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractClauseResponse:
    clause = await get_clause(db, clause_id)
    if not clause:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")
    return ContractClauseResponse.model_validate(clause)


@router.patch("/clauses/{clause_id}", response_model=ContractClauseResponse, summary="Update a clause library entry")
async def update_clause_endpoint(
    clause_id: UUID,
    clause_update: ContractClauseUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractClauseResponse:
    clause = await update_clause(db, clause_id, clause_update)
    if not clause:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")
    return ContractClauseResponse.model_validate(clause)


@router.get("/templates", response_model=ContractTemplateListResponse, summary="List contract templates")
async def list_templates(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    contract_type: str | None = Query(None),
    is_active: bool | None = Query(None),
) -> ContractTemplateListResponse:
    templates = await get_templates(db, skip=skip, limit=limit, contract_type=contract_type, is_active=is_active)
    total = await get_templates_count(db, contract_type=contract_type, is_active=is_active)
    return ContractTemplateListResponse(
        items=[ContractTemplateResponse.model_validate(t) for t in templates], total=total, skip=skip, limit=limit
    )


@router.post(
    "/templates",
    response_model=ContractTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a contract template to the template library",
)
async def create_template_endpoint(
    template_data: ContractTemplateCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractTemplateResponse:
    template = await create_template(db, template_data, created_by=current_user.id)
    return ContractTemplateResponse.model_validate(template)


@router.get("/templates/{template_id}", response_model=ContractTemplateResponse, summary="Get a contract template")
async def get_template_endpoint(
    template_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractTemplateResponse:
    template = await get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return ContractTemplateResponse.model_validate(template)


@router.patch("/templates/{template_id}", response_model=ContractTemplateResponse, summary="Update a contract template")
async def update_template_endpoint(
    template_id: UUID,
    template_update: ContractTemplateUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractTemplateResponse:
    template = await update_template(db, template_id, template_update)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return ContractTemplateResponse.model_validate(template)


@router.get(
    "/{contract_id}",
    response_model=ContractResponse,
    summary="Get contract by ID",
    description="Get contract details by ID",
)
async def get_contract_by_id(
    contract_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractResponse:
    """
    Get contract by ID.

    Args:
        contract_id: Contract UUID
        current_user: Current authenticated user
        db: Database session

    Returns:
        ContractResponse: Contract details

    Raises:
        HTTPException: If contract not found
    """
    contract = await get_contract(db, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )
    return ContractResponse.model_validate(contract)


@router.patch(
    "/{contract_id}",
    response_model=ContractResponse,
    summary="Update contract",
    description="Update contract details",
)
async def update_contract_by_id(
    contract_id: UUID,
    contract_update: ContractUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractResponse:
    """
    Update contract by ID.

    Args:
        contract_id: Contract UUID
        contract_update: Contract update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        ContractResponse: Updated contract details

    Raises:
        HTTPException: If contract not found
    """
    contract = await get_contract(db, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    updated_contract = await update_contract(db, contract_id, contract_update)
    return ContractResponse.model_validate(updated_contract)


@router.delete(
    "/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete contract",
    description="Delete contract by ID",
)
async def delete_contract_by_id(
    contract_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete contract by ID.

    Args:
        contract_id: Contract UUID
        current_user: Current authenticated user
        db: Database session

    Raises:
        HTTPException: If contract not found
    """
    contract = await get_contract(db, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    await delete_contract(db, contract_id)


@router.post(
    "/{contract_id}/transition",
    response_model=ContractResponse,
    summary="Move a contract through authoring/review/approval/activation",
)
async def transition_contract_endpoint(
    request: Request,
    contract_id: UUID,
    transition_data: dict[str, str | dict | None],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractResponse:
    action = str(transition_data.get("action", "submit"))
    contract = await transition_contract(
        db, contract_id, actor_id=current_user.id, action=action, details=transition_data.get("details")
    )
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    # Route submit-for-approval through the generic workflow engine when a
    # WorkflowDefinition is configured for entity_type="contract"; falls back
    # to the plain status flip above when none is (returns None, no-op).
    if action.lower() == "submit":
        from app.services.contract_workflow import start_contract_approval_workflow

        instance = await start_contract_approval_workflow(contract, db, started_by=current_user.id)
        if instance is not None:
            # start_workflow_instance commits, which expires the contract ORM
            # object loaded above -- re-fetch before serializing or
            # model_validate raises MissingGreenlet on expired attributes.
            from app.crud.contract import get_contract as _get_contract

            contract = await _get_contract(db, contract_id)
    return ContractResponse.model_validate(contract)


@router.post(
    "/{contract_id}/clauses",
    response_model=ContractClauseLinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a clause-library entry to a contract",
)
async def link_clause_endpoint(
    contract_id: UUID,
    link_data: ContractClauseLinkCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractClauseLinkResponse:
    contract = await get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    clause = await get_clause(db, link_data.clause_id)
    if not clause:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")

    link = await link_clause_to_contract(db, contract_id, link_data, added_by=current_user.id)
    return ContractClauseLinkResponse.model_validate(link)


@router.post(
    "/{contract_id}/obligations",
    response_model=ContractObligationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a tracked obligation to a contract",
)
async def add_obligation_endpoint(
    contract_id: UUID,
    obligation_data: ContractObligationCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractObligationResponse:
    contract = await get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    obligation = await add_obligation(db, contract_id, obligation_data, created_by=current_user.id)
    return ContractObligationResponse.model_validate(obligation)


@router.patch(
    "/{contract_id}/obligations/{obligation_id}",
    response_model=ContractObligationResponse,
    summary="Update a tracked obligation (e.g. mark completed)",
)
async def update_obligation_endpoint(
    contract_id: UUID,
    obligation_id: UUID,
    obligation_update: ContractObligationUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractObligationResponse:
    obligation = await update_obligation(db, obligation_id, obligation_update)
    if not obligation or obligation.contract_id != contract_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")
    return ContractObligationResponse.model_validate(obligation)


@router.post(
    "/{contract_id}/renew",
    response_model=ContractResponse,
    summary="Renew a contract, extending its end date and recording renewal history",
)
async def renew_contract_endpoint(
    contract_id: UUID,
    renewal_data: ContractRenewalCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> ContractResponse:
    contract = await renew_contract(db, contract_id, renewal_data, processed_by=current_user.id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return ContractResponse.model_validate(contract)