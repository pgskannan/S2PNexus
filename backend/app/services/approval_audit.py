"""Approval audit trail + SLA tracking (Unified Approval Workflow spec Section 4).

Records immutable ApprovalEvent rows for every approval action, computes SLA due
dates from SlaDefinition, measures SlaMetric outcomes on completion, evaluates
breaches, and provides reporting/analytics queries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import cast, desc, func, select, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalEvent, SlaDefinition, SlaMetric
from app.models.workflow import WorkflowTask


def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes even for timezone=True columns; normalize
    to aware UTC so arithmetic with aware `now` never raises."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def record_approval_event(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    document_type: str,
    document_id: UUID,
    workflow_version_id: Optional[UUID] = None,
    node_id: Optional[str] = None,
    node_type: str = "APPROVAL",
    action: str,
    actor_user_id: Optional[UUID] = None,
    actor_role_code: Optional[str] = None,
    comments: Optional[str] = None,
    ai_flags: Optional[list[str]] = None,
    ai_explanation_ref: Optional[str] = None,
) -> ApprovalEvent:
    event = ApprovalEvent(
        tenant_id=tenant_id,
        document_type=document_type,
        document_id=document_id,
        workflow_version_id=workflow_version_id,
        node_id=node_id,
        node_type=node_type,
        action=action,
        actor_user_id=actor_user_id,
        actor_role_code=actor_role_code,
        comments=comments,
        ai_flags=ai_flags,
        ai_explanation_ref=ai_explanation_ref,
    )
    db.add(event)
    return event


async def resolve_sla_definition(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    document_type: str,
    role_code: Optional[str] = None,
    node_type: Optional[str] = None,
) -> Optional[SlaDefinition]:
    query = select(SlaDefinition).where(SlaDefinition.document_type == document_type)
    if tenant_id is not None:
        query = query.where(SlaDefinition.tenant_id == tenant_id)
    if role_code:
        query = query.where(SlaDefinition.role_code == role_code)
    elif node_type:
        query = query.where(SlaDefinition.node_type == node_type)
    result = await db.execute(query.order_by(SlaDefinition.created_at.desc()).limit(1))
    return result.scalar_one_or_none()


async def compute_sla_due_at(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    document_type: str,
    role_code: Optional[str] = None,
    node_type: Optional[str] = None,
) -> tuple[Optional[datetime], Optional[UUID]]:
    """Return (sla_due_at, sla_id) for a new node/task, or (None, None) when no
    SLA definition applies."""
    sla = await resolve_sla_definition(
        db, tenant_id=tenant_id, document_type=document_type, role_code=role_code, node_type=node_type
    )
    if sla is None:
        return None, None
    due_at = datetime.now(timezone.utc) + timedelta(minutes=sla.target_duration_minutes)
    return due_at, sla.id


async def record_sla_metric(
    db: AsyncSession,
    *,
    document_id: UUID,
    node_id: Optional[str] = None,
    task_id: Optional[UUID] = None,
    sla_id: Optional[UUID] = None,
    actual_duration_minutes: int,
    breach_flag: bool = False,
    breach_reason: Optional[str] = None,
) -> SlaMetric:
    metric = SlaMetric(
        document_id=document_id,
        node_id=node_id,
        task_id=task_id,
        sla_id=sla_id,
        actual_duration_minutes=actual_duration_minutes,
        breach_flag=breach_flag,
        breach_reason=breach_reason,
    )
    db.add(metric)
    return metric


async def record_task_sla_metric(db: AsyncSession, task: WorkflowTask) -> None:
    """Measure and store an SLA metric for a completed task (spec Section 4 step 3)."""
    if task.created_at is None or task.completed_at is None:
        return
    if task.due_at is None:
        return
    completed = _aware(task.completed_at)
    created = _aware(task.created_at)
    actual_minutes = int((completed - created).total_seconds() // 60)
    breach = completed > _aware(task.due_at)
    await record_sla_metric(
        db,
        document_id=task.instance.entity_id,
        node_id=str(task.step_index),
        task_id=task.id,
        actual_duration_minutes=actual_minutes,
        breach_flag=breach,
        breach_reason="exceeded SLA target" if breach else None,
    )


async def evaluate_sla_breaches(db: AsyncSession) -> list[WorkflowTask]:
    """SLA job: find pending tasks past their due_at, mark breach metrics, and
    return the breached tasks for escalation (spec Section 4 step 2)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(WorkflowTask).where(
            WorkflowTask.status == "pending",
            WorkflowTask.due_at.is_not(None),
            WorkflowTask.due_at < now,
        )
    )
    breached = list(result.scalars().all())
    for task in breached:
        created = _aware(task.created_at) if task.created_at else None
        actual_minutes = int((now - created).total_seconds() // 60) if created else 0
        await record_sla_metric(
            db,
            document_id=task.instance.entity_id,
            node_id=str(task.step_index),
            task_id=task.id,
            actual_duration_minutes=actual_minutes,
            breach_flag=True,
            breach_reason="SLA breach: task overdue",
        )
    if breached:
        await db.commit()
    return breached


async def get_approval_events(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID] = None,
    document_type: Optional[str] = None,
    document_id: Optional[UUID] = None,
    limit: int = 100,
) -> list[ApprovalEvent]:
    query = select(ApprovalEvent)
    if tenant_id is not None:
        query = query.where(ApprovalEvent.tenant_id == tenant_id)
    if document_type:
        query = query.where(ApprovalEvent.document_type == document_type)
    if document_id:
        query = query.where(ApprovalEvent.document_id == document_id)
    query = query.order_by(desc(ApprovalEvent.timestamp)).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_sla_metrics(
    db: AsyncSession, *, tenant_id: Optional[UUID] = None, document_id: Optional[UUID] = None, limit: int = 100
) -> list[SlaMetric]:
    query = select(SlaMetric)
    if document_id:
        query = query.where(SlaMetric.document_id == document_id)
    query = query.order_by(desc(SlaMetric.created_at)).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_approval_analytics(db: AsyncSession) -> dict[str, Any]:
    """Reporting (spec Section 4): average approval time by document type and
    SLA breach rate by role (derived from completed tasks' metrics)."""
    avg_rows = (
        await db.execute(
            select(
                WorkflowTask.step_name,
                func.avg(func.julianday(WorkflowTask.completed_at) - func.julianday(WorkflowTask.created_at)).label("avg_days"),
                func.count(WorkflowTask.id),
            )
            .where(WorkflowTask.completed_at.is_not(None))
            .group_by(WorkflowTask.step_name)
        )
    ).all()
    avg_by_type = [
        {"node": r.step_name, "avg_approval_hours": round((r.avg_days or 0) * 24, 2), "count": r[2]} for r in avg_rows
    ]

    breach_rows = (
        await db.execute(
            select(
                SlaMetric.node_id,
                func.sum(cast(SlaMetric.breach_flag, Integer)).label("breaches"),
                func.count(SlaMetric.id).label("total"),
            ).group_by(SlaMetric.node_id)
        )
    ).all()
    breach_by_node = [
        {"node": r.node_id, "breach_rate": round((r.breaches / r.total * 100), 2) if r.total else 0.0, "total": r.total}
        for r in breach_rows
    ]

    total = (
        await db.execute(select(func.count(SlaMetric.id), func.sum(cast(SlaMetric.breach_flag, Integer))))
    ).one()
    return {
        "avg_approval_time_by_type": avg_by_type,
        "sla_breach_rate_by_node": breach_by_node,
        "total_sla_metrics": total[0] or 0,
        "total_sla_breaches": total[1] or 0,
    }
