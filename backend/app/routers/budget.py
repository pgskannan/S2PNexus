"""Tenant-admin budget configuration API (Phase 5).

Mirrors app.routers.document_numbering's admin-gating pattern
(_require_admin) and endpoint shape.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.budget import (
    check_budget_availability,
    create_budget,
    get_budget,
    list_budgets,
    update_budget,
)
from app.database.session import get_db
from app.models.accounting_split import Budget
from app.models.user import User, UserRole
from app.schemas.budget import (
    BudgetCheckResponse,
    BudgetCreate,
    BudgetListResponse,
    BudgetResponse,
    BudgetUpdate,
)
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/budgets", tags=["Budgets"])


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can manage budgets")


@router.get("", response_model=BudgetListResponse, status_code=status.HTTP_200_OK)
async def list_budgets_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    fiscal_year: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> BudgetListResponse:
    items = await list_budgets(db, tenant_id=current_user.tenant_id, fiscal_year=fiscal_year)
    return BudgetListResponse(items=[BudgetResponse.model_validate(b) for b in items])


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget_endpoint(
    payload: BudgetCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    _require_admin(current_user)
    try:
        budget = await create_budget(
            db,
            tenant_id=current_user.tenant_id,
            fiscal_year=payload.fiscal_year,
            fiscal_period=payload.fiscal_period,
            scope_level=payload.scope_level,
            scope_code=payload.scope_code,
            budgeted_amount=payload.budgeted_amount,
            enforcement=payload.enforcement,
            created_by=current_user.id,
        )
    except Exception as exc:  # noqa: BLE001 - surface unique-constraint violations as 400s
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A budget already exists for this tenant/fiscal_year/fiscal_period/scope, or the input was invalid",
        ) from exc
    return BudgetResponse.model_validate(budget)


@router.get("/check", response_model=BudgetCheckResponse, status_code=status.HTTP_200_OK)
async def check_budget_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    requested_amount: Decimal = Query(..., gt=0),
    gl_account_code: Optional[str] = Query(default=None),
    cost_center: Optional[str] = Query(default=None),
    fiscal_year: Optional[int] = Query(default=None),
    fiscal_period: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> BudgetCheckResponse:
    if not gl_account_code and not cost_center:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one of gl_account_code or cost_center is required")
    now = datetime.now(timezone.utc)
    result = await check_budget_availability(
        db,
        current_user.tenant_id,
        gl_account_code,
        cost_center,
        fiscal_year or now.year,
        fiscal_period,
        requested_amount,
    )
    return BudgetCheckResponse.model_validate(result)


@router.get("/{budget_id}", response_model=BudgetResponse, status_code=status.HTTP_200_OK)
async def get_budget_endpoint(
    budget_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    budget = await get_budget(db, budget_id, tenant_id=current_user.tenant_id)
    if not budget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return BudgetResponse.model_validate(budget)


@router.put("/{budget_id}", response_model=BudgetResponse, status_code=status.HTTP_200_OK)
async def update_budget_endpoint(
    budget_id: UUID,
    payload: BudgetUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    _require_admin(current_user)
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    budget = await update_budget(db, budget_id, current_user.tenant_id, updates)
    if not budget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return BudgetResponse.model_validate(budget)
