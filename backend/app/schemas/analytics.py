"""
Analytics schemas for S2PNexus.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SpendByCategory(BaseModel):
    """Spend by category."""

    model_config = ConfigDict(from_attributes=True)

    category: str
    amount: Decimal
    percentage: float


class SpendByMonth(BaseModel):
    """Spend by month."""

    model_config = ConfigDict(from_attributes=True)

    month: str  # YYYY-MM format
    amount: Decimal


class TopSupplier(BaseModel):
    """Top supplier spend."""

    model_config = ConfigDict(from_attributes=True)

    supplier_id: UUID
    supplier_name: str
    total_spend: Decimal
    contract_count: int


class DashboardMetricsResponse(BaseModel):
    """Dashboard metrics response."""

    model_config = ConfigDict(from_attributes=True)

    total_spend: Decimal
    total_suppliers: int
    total_contracts: int
    active_contracts: int
    expiring_contracts: int
    pending_approvals: int
    spend_by_category: list[SpendByCategory]
    spend_by_month: list[SpendByMonth]
    top_suppliers: list[TopSupplier]


class SpendAnalyticsResponse(BaseModel):
    """Spend analytics response."""

    model_config = ConfigDict(from_attributes=True)

    total_spend: Decimal
    spend_by_category: list[SpendByCategory]
    spend_by_month: list[SpendByMonth]
    top_suppliers: list[TopSupplier]
    period_start: date
    period_end: date


class SupplierAnalyticsResponse(BaseModel):
    """Supplier analytics response."""

    model_config = ConfigDict(from_attributes=True)

    supplier_id: Optional[UUID] = None
    supplier_name: Optional[str] = None
    total_contracts: int
    active_contracts: int
    total_spend: Decimal
    avg_contract_value: Decimal
    contract_types: dict[str, int]
    spend_trend: list[SpendByMonth]
    # P2P UX backlog Section 4: supplier performance scorecard (PO / receipt
    # based performance, on top of the contract/spend analytics above).
    performance_scorecard: "SupplierPerformanceScorecard" = Field(default_factory=lambda: SupplierPerformanceScorecard())


class ContractAnalyticsResponse(BaseModel):
    """Contract analytics response."""

    model_config = ConfigDict(from_attributes=True)

    total_contracts: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    expiring_soon: int
    total_value: Decimal
    avg_value: Decimal


# ---------------------------------------------------------------------------
# P2P UX backlog Section 4: Reports & Analytics
# ---------------------------------------------------------------------------


class SupplierPerformanceScorecard(BaseModel):
    """PO/receipt-based supplier performance metrics (extends supplier
    analytics — the scorecard report reuses this shape)."""

    model_config = ConfigDict(from_attributes=True)

    total_purchase_orders: int = 0
    open_purchase_orders: int = 0
    po_value: Decimal = Decimal("0")
    receipt_count: int = 0
    exception_receipt_count: int = 0
    exception_rate: float = 0.0
    total_received_quantity: Decimal = Decimal("0")
    rejected_quantity: Decimal = Decimal("0")
    risk_level: Optional[str] = None
    lifecycle_status: Optional[str] = None


class SupplierScorecardEntry(SupplierPerformanceScorecard):
    """One row of the org-wide supplier performance scorecard report."""

    supplier_id: UUID
    supplier_name: str
    total_spend: Decimal = Decimal("0")
    total_contracts: int = 0


class SupplierScorecardResponse(BaseModel):
    """GET /analytics/supplier-scorecard — per-supplier performance rows."""

    items: list[SupplierScorecardEntry]
    total: int


class PoAgingBucket(BaseModel):
    """Count + value of open POs in one age bucket and lifecycle status."""

    bucket: str  # "0-7" | "8-14" | "15-30" | "30+"
    lifecycle_status: str
    count: int
    total_value: Decimal


class PoAgingResponse(BaseModel):
    """GET /analytics/po-aging — open POs (not closed/cancelled) bucketed by
    age = now - created_at."""

    as_of: date
    buckets: list[PoAgingBucket]
    by_lifecycle_status: dict[str, int]
    total_count: int
    total_value: Decimal


class ApprovalBottleneckTask(BaseModel):
    """One currently-open (pending/blocked) approval task."""

    task_id: UUID
    instance_id: UUID
    step_name: str
    status: str
    assignee_id: Optional[UUID] = None
    age_days: float
    due_at: Optional[datetime] = None
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None


class ApprovalBottleneckResponse(BaseModel):
    """GET /analytics/approval-bottlenecks — where approvals are getting stuck.

    Combines current open-task pressure (pending/blocked/overdue) with the
    historical avg-time and SLA-breach data already shipped by
    /approval/analytics.
    """

    pending_tasks: int
    blocked_tasks: int
    overdue_pending: int
    avg_pending_age_days: float
    oldest_pending: list[ApprovalBottleneckTask]
    slowest_nodes: list[dict]
    breach_by_node: list[dict]
    total_sla_metrics: int
    total_sla_breaches: int


class ExceptionRequisition(BaseModel):
    """One requisition parked in ``lifecycle_status == "exception"`` with the
    blocker reasons that prevented PO auto-creation."""

    requisition_id: UUID
    requisition_number: Optional[str] = None
    title: str
    supplier_id: Optional[UUID] = None
    supplier_name: Optional[str] = None
    estimated_value: Optional[Decimal] = None
    currency: str = "USD"
    reasons: list[str] = []
    last_blocked_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ExceptionDashboardResponse(BaseModel):
    """GET /analytics/exceptions — exception requisitions with blocker reasons."""

    items: list[ExceptionRequisition]
    total: int


class ExceptionRetryResponse(BaseModel):
    """POST /analytics/exceptions/{id}/retry — re-runs PO auto-creation."""

    ok: bool
    requisition_id: UUID
    lifecycle_status: str
    purchase_order_id: Optional[UUID] = None
    reasons: list[str] = []
    message: str