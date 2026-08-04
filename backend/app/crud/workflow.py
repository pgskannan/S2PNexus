"""Workflow Automation engine for S2PNexus.

Executes WorkflowDefinition steps against a WorkflowInstance:
- "condition" steps branch based on a field in the instance's context.
- "approval" steps fan out one WorkflowTask per approver (parallel
  approvals); the step completes once `required_approvals` tasks are
  approved, or the whole instance is rejected on the first rejection.
- "notification" steps create a Notification per recipient.

Escalation is handled out-of-band by `escalate_overdue_tasks`, which is meant
to be invoked periodically (e.g. by a scheduled job) or on-demand via the API.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Notification, WorkflowDefinition, WorkflowInstance, WorkflowTask
from app.schemas.workflow import WorkflowDefinitionCreate, WorkflowInstanceStart
from app.services.approval_audit import compute_sla_due_at, record_approval_event, record_task_sla_metric

_OPERATORS = {
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and a > b,
    "gte": lambda a, b: a is not None and a >= b,
    "lt": lambda a, b: a is not None and a < b,
    "lte": lambda a, b: a is not None and a <= b,
    "in": lambda a, b: a in (b or []),
}
_NUMERIC_OPERATORS = {"gt", "gte", "lt", "lte"}


def _normalize_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _coerce_numeric(value: Any) -> Any:
    """Best-effort numeric coercion for condition comparisons.

    `WorkflowInstance.context` is a plain JSON column with no Decimal/UUID
    encoder, so callers that build context from ORM entities (e.g.
    `services/procurement_workflow.py`) stringify Decimal fields like
    `estimated_value` before storing them (str(Decimal(...))). Comparing that
    string against a condition step's numeric `value` with `>`/`>=`/`<`/`<=`
    raises TypeError in Python, which `_evaluate_condition` was silently
    swallowing to `False` -- meaning every amount-threshold condition
    (`estimated_value >= 1000`, the standard PR/PO approval-tier pattern)
    always took the false branch, regardless of the real amount. Only used for
    the four ordering operators; `eq`/`neq`/`in` are left alone since they're
    also legitimately used for non-numeric fields (category, status, etc.).
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return value
    if isinstance(value, str):
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            return value
    return value


def _condition_sibling_arm(steps: list[dict[str, Any]], step_index: int) -> tuple[int, int] | None:
    """If `step_index` is one arm of a Yes/No condition diamond, return
    `(sibling_index, merge_index)`.

    `merge_index` is the first step after both arms (`max(true, false) + 1`),
    which is where execution should continue instead of falling linearly from
    one arm into the other. Without this, a diamond like
    `Condition → Yes(2) | No(3)` advances Yes → No via plain `+1` and wrongly
    requires the unused branch. Explicit `next_step` on the arm still wins
    (see `_continue_after_step`).
    """
    for step in steps:
        if step.get("step_type") != "condition":
            continue
        true_t = step.get("on_true_next_step")
        false_t = step.get("on_false_next_step")
        if not isinstance(true_t, int) or not isinstance(false_t, int):
            continue
        if true_t == false_t:
            continue
        if step_index == true_t:
            return false_t, max(true_t, false_t) + 1
        if step_index == false_t:
            return true_t, max(true_t, false_t) + 1
    return None


def _continue_after_step(steps: list[dict[str, Any]], step_index: int) -> int:
    """Index to resume at after a non-branching step finishes.

    Prefer an explicit `next_step` (designer "Continue to" / End). Otherwise
    advance by one, but never fall from one condition arm into its sibling --
    jump to the merge point after both arms instead.
    """
    if step_index < 0 or step_index >= len(steps):
        return len(steps)
    step = steps[step_index]
    explicit = step.get("next_step")
    if isinstance(explicit, int):
        return explicit
    candidate = step_index + 1
    sibling_info = _condition_sibling_arm(steps, step_index)
    if sibling_info is not None:
        sibling, merge = sibling_info
        if candidate == sibling:
            return merge
    return candidate


def _evaluate_condition(step: dict[str, Any], context: dict[str, Any]) -> bool:
    operator_key = step.get("operator", "eq")
    operator = _OPERATORS.get(operator_key)
    if operator is None:
        return False
    actual = context.get(step.get("field"))
    expected = step.get("value")
    if operator_key in _NUMERIC_OPERATORS:
        actual = _coerce_numeric(actual)
        expected = _coerce_numeric(expected)
    try:
        return bool(operator(actual, expected))
    except TypeError:
        return False


# --- Definitions -----------------------------------------------------

async def create_workflow_definition(
    db: AsyncSession, definition_in: WorkflowDefinitionCreate, *, created_by: UUID
) -> WorkflowDefinition:
    steps = [step.model_dump(mode="json") for step in definition_in.steps]
    definition = WorkflowDefinition(
        name=definition_in.name,
        entity_type=definition_in.entity_type,
        description=definition_in.description,
        steps=steps,
        is_active=definition_in.is_active,
        status=definition_in.status or "published",
        created_by=created_by,
    )
    db.add(definition)
    await db.commit()
    await db.refresh(definition)
    return definition


async def set_workflow_definition_status(
    db: AsyncSession, definition_id: UUID | str, *, status: str
) -> Optional[WorkflowDefinition]:
    """Transition a definition between draft / published / archived (spec sec 3)."""
    definition = await get_workflow_definition(db, definition_id)
    if definition is None:
        return None
    if status not in ("draft", "published", "archived"):
        raise ValueError("status must be one of draft, published, archived")
    definition.status = status
    # Published definitions are active; archived are inactive.
    definition.is_active = status == "published"
    await db.commit()
    await db.refresh(definition)
    return definition


async def get_workflow_definitions(
    db: AsyncSession, skip: int = 0, limit: int = 100, entity_type: Optional[str] = None, is_active: Optional[bool] = None
) -> list[WorkflowDefinition]:
    query = select(WorkflowDefinition)
    if entity_type:
        query = query.where(WorkflowDefinition.entity_type == entity_type)
    if is_active is not None:
        query = query.where(WorkflowDefinition.is_active == is_active)
    query = query.order_by(desc(WorkflowDefinition.created_at)).offset(skip).limit(limit)
    try:
        result = await db.execute(query)
        return list(result.scalars().all())
    except OperationalError:
        # Table may not exist in lightweight test DBs; treat as no definitions.
        return []


async def get_workflow_definitions_count(
    db: AsyncSession, entity_type: Optional[str] = None, is_active: Optional[bool] = None
) -> int:
    query = select(func.count(WorkflowDefinition.id))
    if entity_type:
        query = query.where(WorkflowDefinition.entity_type == entity_type)
    if is_active is not None:
        query = query.where(WorkflowDefinition.is_active == is_active)
    try:
        result = await db.execute(query)
        return result.scalar_one()
    except OperationalError:
        return 0


async def get_workflow_definition(db: AsyncSession, definition_id: UUID | str) -> Optional[WorkflowDefinition]:
    result = await db.execute(select(WorkflowDefinition).where(WorkflowDefinition.id == _normalize_uuid(definition_id)))
    return result.scalar_one_or_none()


async def delete_workflow_definition(db: AsyncSession, definition_id: UUID | str) -> bool:
    definition = await get_workflow_definition(db, definition_id)
    if definition is None:
        return False
    await db.delete(definition)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise ValueError("Workflow definitions with execution history cannot be deleted; deactivate them instead")
    return True


# --- Instances / step execution -----------------------------------------------------

async def _create_notification(
    db: AsyncSession, recipient_id: UUID, title: str, message: str, *, entity_type: str, entity_id: UUID
) -> None:
    db.add(
        Notification(
            recipient_id=recipient_id,
            title=title,
            message=message,
            related_entity_type=entity_type,
            related_entity_id=entity_id,
        )
    )


async def _run_from_step(db: AsyncSession, instance: WorkflowInstance, steps: list[dict[str, Any]], step_index: int) -> None:
    """Advance the instance starting at step_index until it completes or reaches
    a step that requires waiting on human input (an approval step)."""
    while True:
        if step_index < 0 or step_index >= len(steps):
            instance.status = "completed"
            instance.completed_at = datetime.now(timezone.utc)
            instance.current_step_index = len(steps)
            if instance.entity_type == "requisition":
                from app.crud.procurement import get_requisition
                from app.services.procurement_workflow import auto_create_po_from_requisition

                requisition = await get_requisition(db, instance.entity_id)
                tenant_id = None
                if requisition is not None:
                    requisition.status = "approved"
                    requisition.lifecycle_status = "approved"
                    requisition.approval_status = "approved"
                    requisition.approved_at = instance.completed_at
                    tenant_id = requisition.tenant_id
                    if db is not None and hasattr(db, "add"):
                        from app.models.procurement import ProcurementAuditEvent

                        db.add(
                            ProcurementAuditEvent(
                                requisition_id=requisition.id,
                                actor_id=instance.started_by,
                                action="workflow:completed",
                                details={"workflow_instance_id": str(instance.id)},
                            )
                        )
                await auto_create_po_from_requisition(
                    db,
                    instance.entity_id,
                    started_by=instance.started_by,
                    tenant_id=tenant_id,
                )
            elif instance.entity_type == "preferred_supplier_review":
                # Template Framework Phase 4: a completed override-review
                # instance APPLIES the pending manual override that started
                # it (rejection simply never reaches here, leaving the
                # engine-computed status untouched). The pending override
                # lives only in the instance context until this point.
                from app.services.preferred_supplier import apply_preferred_override

                await apply_preferred_override(
                    db,
                    supplier_id=_normalize_uuid(instance.context.get("supplier_id")),
                    target_status=str(instance.context.get("target_status") or ""),
                    reason=instance.context.get("override_reason"),
                    actor_id=_normalize_uuid(instance.context.get("override_by")),
                    tenant_id=_normalize_uuid(instance.context.get("tenant_id")) if instance.context.get("tenant_id") else None,
                    commit=False,  # this function's caller owns the transaction
                )
            elif instance.entity_type == "supplier_request":
                # Supplier Type / Excel Registration Phase 2 (FS 5.2 steps
                # 5-6): approving a supplier_request previously did nothing
                # beyond flipping its own status -- this is the missing
                # Supplier-creation + registration-trigger link.
                from app.services.registration_trigger import on_supplier_request_approved

                await on_supplier_request_approved(db, instance.entity_id, actor_id=instance.started_by, commit=False)
            elif instance.entity_type == "supplier_registration_pending":
                # MANUAL registration_mode: completing this single-step task
                # (Creator or SLP Admin) sends the workbook. entity_id here is
                # the SupplierRegistration.id, not the SupplierRequest.id.
                from app.services.registration_trigger import send_registration_workbook

                await send_registration_workbook(db, instance.entity_id, actor_id=instance.started_by, commit=False)
            return

        step = steps[step_index]
        instance.current_step_index = step_index
        step_type = step.get("step_type")

        if step.get("parallel_group"):
            group_key = step["parallel_group"]
            member_indices = sorted(i for i, s in enumerate(steps) if s.get("parallel_group") == group_key)

            already_activated = (
                await db.execute(
                    select(WorkflowTask.id).where(
                        WorkflowTask.instance_id == instance.id,
                        WorkflowTask.step_index.in_(member_indices),
                    )
                )
            ).first() is not None

            if not already_activated:
                any_unresolved = False
                for member_index in member_indices:
                    member_step = steps[member_index]
                    member_type = member_step.get("step_type")
                    if member_type == "approval":
                        created, self_approval_only = await _create_approval_tasks(db, instance, member_step, member_index)
                        if not created and not self_approval_only:
                            # Same principle as the non-parallel approval path
                            # below: a member that can't resolve any approver
                            # (e.g. its role_code's ApproverSeed got
                            # deactivated after this definition was
                            # published -- the schema validator can't catch
                            # that ahead of time) must not be silently
                            # treated as "satisfied" by
                            # _parallel_group_is_complete, or the group -- and
                            # the whole instance -- could complete with a
                            # branch that no human ever actually signed off
                            # on.
                            any_unresolved = True
                        # self_approval_only: the sole resolvable approver for
                        # this branch is the requester themself -- treat the
                        # branch as not-required rather than blocking the
                        # whole parallel group on a task no one could ever
                        # complete (mirrors the sequential-step escalation
                        # below, minus the "advance to next tier" part since
                        # parallel branches don't have a linear next tier).
                    elif member_type == "notification":
                        template = member_step.get("message_template") or member_step.get("name") or "Workflow notification"
                        message = (
                            template.format(**instance.context) if _safe_format(template, instance.context) else template
                        )
                        for recipient in member_step.get("recipients", []):
                            await _create_notification(
                                db,
                                _normalize_uuid(recipient),
                                title=member_step.get("name", "Workflow notification"),
                                message=message,
                                entity_type=instance.entity_type,
                                entity_id=instance.entity_id,
                            )
                    elif member_type == "auto":
                        await record_approval_event(
                            db,
                            tenant_id=instance.context.get("tenant_id"),
                            document_type=instance.entity_type,
                            document_id=instance.entity_id,
                            workflow_version_id=instance.definition_id,
                            node_id=str(member_index),
                            node_type="AUTO",
                            action="AUTO_APPROVED",
                            comments=member_step.get("name", "Auto-approval"),
                        )
                    # "condition"/"ai" aren't valid parallel_group members --
                    # rejected at the schema level (WorkflowDefinitionCreate's
                    # _validate_parallel_groups), so nothing to handle here.

                if any_unresolved:
                    instance.status = "blocked"
                    instance.current_step_index = step_index
                    await db.flush()
                    return

            # Newly created tasks must be visible to the completion check below
            # (session autoflush=False in production).
            await db.flush()
            if not await _parallel_group_is_complete(db, instance, steps, member_indices):
                instance.status = "in_progress"
                return  # wait for the remaining branch(es)

            next_step = step.get("parallel_next_step")
            step_index = next_step if next_step is not None else max(member_indices) + 1
            continue

        if step_type == "condition":
            result = _evaluate_condition(step, instance.context)
            next_step = step.get("on_true_next_step") if result else step.get("on_false_next_step")
            step_index = next_step if next_step is not None else step_index + 1
            continue

        if step_type == "notification":
            template = step.get("message_template") or step.get("name") or "Workflow notification"
            message = template.format(**instance.context) if _safe_format(template, instance.context) else template
            for recipient in step.get("recipients", []):
                await _create_notification(
                    db,
                    _normalize_uuid(recipient),
                    title=step.get("name", "Workflow notification"),
                    message=message,
                    entity_type=instance.entity_type,
                    entity_id=instance.entity_id,
                )
            step_index = _continue_after_step(steps, step_index)
            continue

        if step_type == "auto":
            # Deterministic auto-approval node (approval workflow spec sec 3).
            await record_approval_event(
                db,
                tenant_id=instance.context.get("tenant_id"),
                document_type=instance.entity_type,
                document_id=instance.entity_id,
                workflow_version_id=instance.definition_id,
                node_id=str(step_index),
                node_type="AUTO",
                action="AUTO_APPROVED",
                comments=step.get("name", "Auto-approval"),
            )
            step_index = _continue_after_step(steps, step_index)
            continue

        if step_type == "ai":
            # AI node (spec sec 3): evaluate deterministic + AI rules.
            from app.services.approval_rule_engine import evaluate_rules

            decision = evaluate_rules(instance.entity_type, instance.context, {"rules": step.get("rules", {})})
            if decision.get("auto_approve"):
                await record_approval_event(
                    db,
                    tenant_id=instance.context.get("tenant_id"),
                    document_type=instance.entity_type,
                    document_id=instance.entity_id,
                    workflow_version_id=instance.definition_id,
                    node_id=str(step_index),
                    node_type="AI",
                    action="AUTO_APPROVED",
                    comments=step.get("name", "AI auto-approval"),
                    ai_flags=decision.get("ai_flags"),
                    ai_explanation_ref=step.get("name"),
                )
                step_index = _continue_after_step(steps, step_index)
                continue
            # Not auto-approvable: fall through to an approval node for the
            # suggested role (or the role configured on the step).
            step = {
                **step,
                "approvers": [],
                "role_code": decision.get("suggested_role") or step.get("role_code"),
                "name": step.get("name", "Approval"),
            }
            step_type = "approval"

        if step_type == "approval":
            # If this step was already satisfied (e.g. production previously
            # failed to advance after approve because of autoflush=False), skip
            # recreating tasks and continue — repairs stuck instances on the
            # next engine entry (retry or a later approval path).
            existing_statuses = (
                await db.execute(
                    select(WorkflowTask.status).where(
                        WorkflowTask.instance_id == instance.id,
                        WorkflowTask.step_index == step_index,
                    )
                )
            ).scalars().all()
            if existing_statuses:
                required = step.get("required_approvals", 1)
                approved = sum(1 for s in existing_statuses if s == "approved")
                if approved >= required:
                    step_index = _continue_after_step(steps, step_index)
                    continue
                instance.status = "in_progress"
                return  # wait for remaining approvals on this step

            created, self_approval_only = await _create_approval_tasks(db, instance, step, step_index)
            if not created:
                if self_approval_only:
                    # The only resolvable approver(s) for this tier are the
                    # same person who started the instance (e.g. one demo/
                    # seed user per role, and they're also the requester).
                    # complete_task() would reject their own approval anyway
                    # -- auto-escalate to the next tier instead of handing
                    # them a task they can never complete, same as an org
                    # chart routing self-approval up to your manager.
                    step_index = _continue_after_step(steps, step_index)
                    continue
                # No approvers resolvable at all. Never silently skip this
                # node -- skipping would let the instance "complete" with no
                # human sign-off and e.g. auto-create a PO. Block the
                # instance for intervention instead; an admin can fix
                # approver resolution and retry via
                # POST /workflow/instances/{id}/retry.
                instance.status = "blocked"
                instance.current_step_index = step_index
                await db.flush()
                return
            instance.status = "in_progress"
            return  # wait for human input

        # Unknown step type: skip it rather than silently looping forever.
        step_index = _continue_after_step(steps, step_index)


async def _create_approval_tasks(
    db: AsyncSession, instance: WorkflowInstance, step: dict[str, Any], step_index: int
) -> tuple[bool, bool]:
    """Resolve approvers for `step` and create one pending WorkflowTask per
    approver at `step_index`. Shared by the top-level approval-step handling
    and by parallel-group member activation (see _run_from_step) so both
    paths get identical approver resolution, SLA/escalation due-date
    computation, and notification behavior.

    Returns (created, self_approval_only):
    - created=False, self_approval_only=False: no approvers resolved at all
      (e.g. a misconfigured/deactivated role_code) -- callers block the
      instance for admin intervention, they must NOT silently skip this.
    - created=False, self_approval_only=True: at least one approver resolved,
      but every one of them is the same user who started this instance (e.g.
      exactly one demo/seed user for a tier, and they're also the requester).
      complete_task() rejects a requester approving their own request, so
      assigning the task would deadlock it -- callers should instead treat
      this the same as "step satisfied" and advance to the next tier, the
      way an org chart auto-escalates self-approval to your manager.
    """
    approver_ids: list[UUID] = []
    explicit = step.get("approvers") or []
    if explicit:
        approver_ids = [_normalize_uuid(a) for a in explicit]
    elif step.get("role_code"):
        # Rule-driven approver resolution from ApproverSeed master data
        # (spec sec 1 + sec 3): role + limits + scope + primary/backup.
        from app.crud.approval import resolve_approvers_for_context

        resolved = await resolve_approvers_for_context(
            db,
            role_code=step["role_code"],
            amount=Decimal(str(instance.context.get("amount") or "0")),
            category=instance.context.get("category"),
            supplier_id=(str(instance.context["supplier_id"]) if instance.context.get("supplier_id") else None),
            tenant_id=instance.context.get("tenant_id"),
        )
        approver_ids = [UUID(a["user_id"]) for a in resolved]

    had_candidates = bool(approver_ids)
    if instance.started_by is not None:
        approver_ids = [a for a in approver_ids if a != instance.started_by]

    if not approver_ids:
        return False, had_candidates

    escalate_after_hours = step.get("escalate_after_hours")
    due_at = None
    sla_due, _sla_id = await compute_sla_due_at(
        db,
        tenant_id=instance.context.get("tenant_id"),
        document_type=instance.entity_type,
        role_code=step.get("role_code"),
    )
    if sla_due is not None:
        due_at = sla_due
    elif escalate_after_hours:
        due_at = datetime.now(timezone.utc) + timedelta(hours=escalate_after_hours)

    for approver_id in approver_ids:
        db.add(
            WorkflowTask(
                instance_id=instance.id,
                step_index=step_index,
                step_name=step.get("name", "Approval"),
                # Snapshot the step's "why" so the approver sees it even if the
                # definition is later edited/versioned.
                reason=step.get("reason"),
                assignee_id=approver_id,
                status="pending",
                due_at=due_at,
                escalate_to=_normalize_uuid(step["escalate_to"]) if step.get("escalate_to") else None,
            )
        )
        await _create_notification(
            db,
            approver_id,
            title=f"Approval requested: {step.get('name', 'Approval')}",
            message=f"Your approval is requested for {instance.entity_type} {instance.entity_id}.",
            entity_type=instance.entity_type,
            entity_id=instance.entity_id,
        )
    return True, False


async def _parallel_group_is_complete(
    db: AsyncSession, instance: WorkflowInstance, steps: list[dict[str, Any]], member_indices: list[int]
) -> bool:
    """A parallel group is complete once every member that actually created
    WorkflowTask rows (i.e. was an approval-type member with resolvable
    approvers) has reached its own required_approvals. Members that never
    created tasks (notification/auto, or an approval member with zero
    resolvable approvers) are treated as instantly resolved -- same
    "skip rather than hang" convention as the non-parallel approval path."""
    for member_index in member_indices:
        statuses = (
            await db.execute(
                select(WorkflowTask.status).where(
                    WorkflowTask.instance_id == instance.id,
                    WorkflowTask.step_index == member_index,
                )
            )
        ).scalars().all()
        if not statuses:
            continue
        required = steps[member_index].get("required_approvals", 1)
        approved = sum(1 for s in statuses if s == "approved")
        if approved < required:
            return False
    return True


def _safe_format(template: Optional[str], context: dict[str, Any]) -> bool:
    if not template:
        return False
    try:
        template.format(**context)
        return True
    except (KeyError, IndexError):
        return False


async def start_workflow_instance(
    db: AsyncSession,
    start_in: WorkflowInstanceStart,
    *,
    started_by: UUID,
    definition_steps_override: list[dict[str, Any]] | None = None,
) -> WorkflowInstance:
    definition = await get_workflow_definition(db, start_in.definition_id)
    if not definition:
        raise ValueError("Workflow definition not found")
    if not definition.is_active:
        raise ValueError("Workflow definition is not active")

    instance = WorkflowInstance(
        definition_id=definition.id,
        entity_type=start_in.entity_type,
        entity_id=start_in.entity_id,
        status="in_progress",
        current_step_index=0,
        context=start_in.context,
        started_by=started_by,
    )
    db.add(instance)
    await db.flush()

    steps = definition_steps_override if definition_steps_override is not None else definition.steps
    await _run_from_step(db, instance, steps, 0)

    await db.commit()
    await db.refresh(instance)
    return instance


async def retry_blocked_instance(db: AsyncSession, instance_id: UUID | str) -> Optional[WorkflowInstance]:
    """Re-run a stalled workflow instance from the step it is on.

    Supports:
    - `blocked` instances (approver resolution failed)
    - `in_progress` instances stuck with no pending tasks after an already-
      satisfied approval (the autoflush=False count bug left Initial approved
      but never advanced to the next step)

    Healthy in-progress instances that still have pending tasks are left alone
    (returns None) so Retry cannot be used to duplicate work.
    """
    instance = await get_workflow_instance(db, instance_id)
    if not instance or instance.status not in ("blocked", "in_progress"):
        return None

    definition = await get_workflow_definition(db, instance.definition_id)
    if not definition:
        return None

    if instance.status == "in_progress":
        pending = (
            await db.execute(
                select(WorkflowTask.id).where(
                    WorkflowTask.instance_id == instance.id,
                    WorkflowTask.status.in_(["pending", "escalated"]),
                )
            )
        ).first()
        if pending is not None:
            return None  # healthy — still waiting on an assignee

    # Cancel any stray pending tasks on blocked instances (a blocked instance
    # normally has none, but be defensive -- e.g. a parallel-group sibling
    # left waiting).
    if instance.status == "blocked":
        result = await db.execute(
            select(WorkflowTask).where(
                WorkflowTask.instance_id == instance.id,
                WorkflowTask.status == "pending",
            )
        )
        for task in result.scalars().all():
            task.status = "cancelled"

    instance.status = "in_progress"
    await _run_from_step(db, instance, definition.steps, instance.current_step_index)
    await db.commit()
    await db.refresh(instance)
    return instance


async def get_workflow_instance(db: AsyncSession, instance_id: UUID | str) -> Optional[WorkflowInstance]:
    result = await db.execute(select(WorkflowInstance).where(WorkflowInstance.id == _normalize_uuid(instance_id)))
    return result.scalar_one_or_none()


async def get_workflow_instances(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    entity_type: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    status: Optional[str] = None,
) -> list[WorkflowInstance]:
    query = select(WorkflowInstance)
    if entity_type:
        query = query.where(WorkflowInstance.entity_type == entity_type)
    if entity_id:
        query = query.where(WorkflowInstance.entity_id == entity_id)
    if status:
        query = query.where(WorkflowInstance.status == status)
    query = query.order_by(desc(WorkflowInstance.started_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_workflow_instances_count(
    db: AsyncSession, entity_type: Optional[str] = None, entity_id: Optional[UUID] = None, status: Optional[str] = None
) -> int:
    query = select(func.count(WorkflowInstance.id))
    if entity_type:
        query = query.where(WorkflowInstance.entity_type == entity_type)
    if entity_id:
        query = query.where(WorkflowInstance.entity_id == entity_id)
    if status:
        query = query.where(WorkflowInstance.status == status)
    result = await db.execute(query)
    return result.scalar_one()


# --- Human tasks -----------------------------------------------------

async def get_workflow_task(db: AsyncSession, task_id: UUID | str) -> Optional[WorkflowTask]:
    result = await db.execute(select(WorkflowTask).where(WorkflowTask.id == _normalize_uuid(task_id)))
    return result.scalar_one_or_none()


async def get_my_tasks(db: AsyncSession, assignee_id: UUID, status: Optional[str] = "pending") -> list[WorkflowTask]:
    query = select(WorkflowTask).where(WorkflowTask.assignee_id == assignee_id)
    if status:
        query = query.where(WorkflowTask.status == status)
    query = query.order_by(WorkflowTask.due_at.is_(None), WorkflowTask.due_at, desc(WorkflowTask.created_at))
    result = await db.execute(query)
    return list(result.scalars().all())


async def complete_task(
    db: AsyncSession, task_id: UUID | str, *, actor_id: UUID, decision: str, comments: Optional[str] = None
) -> Optional[WorkflowTask]:
    task = await get_workflow_task(db, task_id)
    if not task:
        return None
    if task.status != "pending":
        raise ValueError(f"Task is already '{task.status}' and cannot be completed again")

    now = datetime.now(timezone.utc)
    task.status = "approved" if decision == "approve" else "rejected"
    task.completed_by = actor_id
    task.completed_at = now
    task.comments = comments
    # Production AsyncSession uses autoflush=False (database.py). Without an
    # explicit flush, the COUNT / cancel SELECTs below still see the old
    # "pending" row, so approved_count stays 0 and _run_from_step never runs
    # -- leaving the next approval (e.g. Yes Approval for Kannan) stuck as
    # Waiting / Pending assignment with no WorkflowTask.
    await db.flush()

    instance = await get_workflow_instance(db, task.instance_id)
    if instance.entity_type == "requisition":
        from app.crud.procurement import get_requisition as get_procurement_requisition

        requisition = await get_procurement_requisition(db, instance.entity_id)
        if requisition is not None and actor_id == requisition.requested_by:
            raise ValueError("Requisition creator cannot approve their own request")

    definition = await get_workflow_definition(db, instance.definition_id)
    step = definition.steps[task.step_index]

    if decision == "reject":
        instance.status = "rejected"
        instance.completed_at = now
        if instance.entity_type == "requisition":
            from app.crud.procurement import get_requisition

            requisition = await get_requisition(db, instance.entity_id)
            if requisition is not None:
                requisition.status = "rejected"
                requisition.lifecycle_status = "rejected"
                requisition.approval_status = "rejected"
                requisition.rejected_at = now
                from app.models.procurement import ProcurementAuditEvent

                db.add(
                    ProcurementAuditEvent(
                        requisition_id=requisition.id,
                        actor_id=actor_id,
                        action="workflow:rejected",
                        details={"task_id": str(task.id), "comments": comments},
                    )
                )
        elif instance.entity_type == "supplier_request":
            from app.crud.supplier_request import get_supplier_request as _get_supplier_request
            from app.models.supplier_audit import SupplierAuditEvent

            supplier_request = await _get_supplier_request(db, instance.entity_id)
            if supplier_request is not None:
                supplier_request.status = "rejected"
                supplier_request.lifecycle_status = "rejected"
                supplier_request.approval_status = "rejected"
                db.add(
                    SupplierAuditEvent(
                        entity_type="supplier_request",
                        entity_id=supplier_request.id,
                        actor_id=actor_id,
                        action="workflow:rejected",
                        details={"task_id": str(task.id), "comments": comments},
                        tenant_id=supplier_request.tenant_id,
                    )
                )
        # Cancel any other still-pending tasks so they don't linger. For a
        # parallel-group member this spans every sibling branch (a rejection
        # anywhere in the group rejects the whole instance, same as a
        # rejection on a lone approval step does), not just this step_index.
        cancel_indices = [task.step_index]
        if step.get("parallel_group"):
            cancel_indices = [i for i, s in enumerate(definition.steps) if s.get("parallel_group") == step["parallel_group"]]
        result = await db.execute(
            select(WorkflowTask).where(
                WorkflowTask.instance_id == instance.id,
                WorkflowTask.step_index.in_(cancel_indices),
                WorkflowTask.status == "pending",
            )
        )
        for other in result.scalars().all():
            other.status = "cancelled"
    else:
        approved_count_result = await db.execute(
            select(func.count(WorkflowTask.id)).where(
                WorkflowTask.instance_id == instance.id,
                WorkflowTask.step_index == task.step_index,
                WorkflowTask.status == "approved",
            )
        )
        approved_count = approved_count_result.scalar_one()
        required = step.get("required_approvals", 1)
        if approved_count >= required:
            # For a parallel-group member, re-enter _run_from_step AT this
            # same member's index rather than continuing -- the parallel_group
            # branch there re-derives the sibling member indices, sees tasks
            # already exist (so it won't recreate them), and only advances past
            # the whole group once _parallel_group_is_complete() is true for
            # every member (this one now included). Non-parallel approvals use
            # `_continue_after_step` so a Yes-branch arm does not fall into
            # its No sibling (and so an explicit `next_step` is honored).
            resume_index = (
                task.step_index
                if step.get("parallel_group")
                else _continue_after_step(definition.steps, task.step_index)
            )
            await _run_from_step(db, instance, definition.steps, resume_index)

    if instance.entity_type == "requisition" and decision == "approve":
        from app.models.procurement import ProcurementAuditEvent

        db.add(
            ProcurementAuditEvent(
                requisition_id=instance.entity_id,
                actor_id=actor_id,
                action="workflow:approved",
                details={"task_id": str(task.id), "comments": comments},
            )
        )

    # Approval audit trail + SLA metric (Unified Approval Workflow spec sec 4).
    actor_role_code = None
    try:
        from app.crud.approval import list_approver_seeds

        seeds = await list_approver_seeds(db, role_code=None, active_only=False, limit=1)
        from app.models.approval import ApproverSeed
        from sqlalchemy import select as _select

        seed = (
            await db.execute(_select(ApproverSeed).where(ApproverSeed.user_id == actor_id, ApproverSeed.active_flag.is_(True)).limit(1))
        ).scalar_one_or_none()
        if seed is not None:
            actor_role_code = seed.role_code
    except Exception:
        actor_role_code = None

    await record_approval_event(
        db,
        tenant_id=instance.context.get("tenant_id"),
        document_type=instance.entity_type,
        document_id=instance.entity_id,
        workflow_version_id=instance.definition_id,
        node_id=str(task.step_index),
        node_type="APPROVAL",
        action="APPROVED" if decision == "approve" else "REJECTED",
        actor_user_id=actor_id,
        actor_role_code=actor_role_code,
        comments=comments,
    )
    await record_task_sla_metric(db, task)

    await db.commit()
    await db.refresh(task)
    return task


async def admin_remove_task(
    db: AsyncSession, task_id: UUID | str, *, actor_id: UUID, reason: Optional[str] = None
) -> Optional[WorkflowTask]:
    """Admin override: remove a pending approval node so the document advances
    to its next status without waiting on that approver (spec: "Admin can
    delete the approval node and document need to go next status").

    Deliberately reuses `complete_task`'s "approve" path rather than adding a
    parallel status/continuation code path -- that function already owns the
    required-approvals counting, parallel-group handling, `_run_from_step`
    continuation, requisition audit event, and ApprovalEvent/SLA logging, all
    of which an admin-remove needs to trigger identically to a real approval
    for the instance to advance correctly. The removal is still fully
    traceable: `actor_id` is the admin (not the original assignee), and the
    comment is prefixed so it reads as an override, not a genuine approval,
    in the approval flow diagram and audit trail.
    """
    task = await get_workflow_task(db, task_id)
    if not task:
        return None
    if task.status != "pending":
        raise ValueError(f"Task is already '{task.status}' and cannot be removed")

    comment = "Approval step removed by admin" + (f": {reason}" if reason else "")
    return await complete_task(db, task_id, actor_id=actor_id, decision="approve", comments=comment)


async def escalate_overdue_tasks(db: AsyncSession) -> list[WorkflowTask]:
    """Escalate every pending task past its due_at that hasn't been escalated yet.

    Meant to be called periodically (or on-demand via the API) since this
    codebase doesn't yet have a background scheduler.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(WorkflowTask).where(
            WorkflowTask.status == "pending",
            WorkflowTask.due_at.is_not(None),
            WorkflowTask.due_at < now,
            WorkflowTask.escalated_at.is_(None),
        )
    )
    overdue = list(result.scalars().all())
    escalated: list[WorkflowTask] = []

    for task in overdue:
        if not task.escalate_to:
            continue
        task.escalated_at = now
        task.status = "escalated"

        instance = await get_workflow_instance(db, task.instance_id)
        # Give the escalation target a fresh, actionable task.
        new_task = WorkflowTask(
            instance_id=task.instance_id,
            step_index=task.step_index,
            step_name=f"{task.step_name} (escalated)",
            assignee_id=task.escalate_to,
            status="pending",
        )
        db.add(new_task)
        await _create_notification(
            db,
            task.escalate_to,
            title=f"Escalated: {task.step_name}",
            message=f"An overdue approval for {instance.entity_type} {instance.entity_id} has been escalated to you.",
            entity_type=instance.entity_type,
            entity_id=instance.entity_id,
        )
        escalated.append(task)

    if escalated:
        await db.commit()
    return escalated


async def process_registration_sla_reminders(db: AsyncSession) -> int:
    """Emit in-app SLA reminder notifications for open Excel registrations.

    Hooks into the same on-demand/scheduled pattern as escalate_overdue_tasks
    (no second cron). For each registration with status=sent and sla_due_at
    set, fires a reminder when today crosses a reminder_at_days offset from
    send (from SupplierType.notification_rule), and an escalation notice at
    escalation_at_days / sla_due_at. Dedupes via a lightweight check on
    existing Notification titles for the registration.
    """
    from app.models.supplier_registration import SupplierRegistration
    from app.models.supplier_type import SupplierType

    now = datetime.now(timezone.utc)
    rows = list(
        (
            await db.execute(
                select(SupplierRegistration).where(
                    SupplierRegistration.status == "sent",
                    SupplierRegistration.workbook_sent_at.is_not(None),
                    SupplierRegistration.sla_due_at.is_not(None),
                )
            )
        ).scalars().all()
    )
    sent = 0
    for reg in rows:
        supplier_type = None
        if reg.supplier_type_id:
            supplier_type = (
                await db.execute(select(SupplierType).where(SupplierType.id == reg.supplier_type_id))
            ).scalar_one_or_none()
        rule = (supplier_type.notification_rule if supplier_type else None) or {}
        reminder_days = rule.get("reminder_at_days") or []
        sent_at = reg.workbook_sent_at
        if sent_at is None:
            continue
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        elapsed_days = (now - sent_at).days
        titles_to_send: list[str] = []
        for day in reminder_days:
            if elapsed_days >= int(day):
                titles_to_send.append(f"Registration SLA reminder (day {day}): {reg.registration_number}")
        if reg.sla_due_at:
            due = reg.sla_due_at if reg.sla_due_at.tzinfo else reg.sla_due_at.replace(tzinfo=timezone.utc)
            if now >= due:
                titles_to_send.append(f"Registration SLA escalation: {reg.registration_number}")

        for title in titles_to_send:
            existing = (
                await db.execute(
                    select(Notification.id).where(
                        Notification.recipient_id == reg.submitted_by,
                        Notification.related_entity_id == reg.id,
                        Notification.title == title,
                    )
                )
            ).first()
            if existing:
                continue
            await _create_notification(
                db,
                reg.submitted_by,
                title=title,
                message=f"Registration {reg.registration_number} for {reg.company_name} needs attention.",
                entity_type="supplier_registration",
                entity_id=reg.id,
            )
            sent += 1
    if sent:
        await db.commit()
    return sent


# --- Notifications -----------------------------------------------------

async def get_notifications(
    db: AsyncSession, recipient_id: UUID, skip: int = 0, limit: int = 100, unread_only: bool = False
) -> list[Notification]:
    query = select(Notification).where(Notification.recipient_id == recipient_id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    query = query.order_by(desc(Notification.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_notifications_count(db: AsyncSession, recipient_id: UUID, unread_only: bool = False) -> int:
    query = select(func.count(Notification.id)).where(Notification.recipient_id == recipient_id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    result = await db.execute(query)
    return result.scalar_one()


async def mark_notification_read(db: AsyncSession, notification_id: UUID | str, *, recipient_id: UUID) -> Optional[Notification]:
    result = await db.execute(
        select(Notification).where(Notification.id == _normalize_uuid(notification_id), Notification.recipient_id == recipient_id)
    )
    notification = result.scalar_one_or_none()
    if not notification:
        return None
    notification.is_read = True
    notification.read_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(notification)
    return notification
