"""Supplier Request approval → Supplier creation → registration trigger (FS 5.2 steps 5-6).

Ad-hoc tasks (FS Section 10) use a WorkflowInstance wrapper (entity_type
supplier_adhoc_task / supplier_registration_pending) so
/workflow/tasks/{id}/complete and notification wiring stay free — no parallel
AdHocTask model.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier
from app.models.supplier_audit import SupplierAuditEvent
from app.models.supplier_registration import SupplierRegistration
from app.models.supplier_request import SupplierRequest
from app.models.supplier_type import MODULE_CODE_TO_TEMPLATE, SupplierType
from app.models.workflow import Notification, WorkflowDefinition, WorkflowInstance
from app.services.excel_registration import (
    QUESTIONNAIRE_VERSION,
    TEMPLATE_VERSION,
    generate_registration_workbook,
)
from app.services import file_storage
from app.services.template_engine import evaluate_visibility, get_effective_template, score_response


def _audit(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: UUID,
    actor_id: Optional[UUID],
    action: str,
    details: dict | None = None,
    tenant_id: Optional[UUID] = None,
) -> None:
    db.add(
        SupplierAuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            action=action,
            details=details,
            tenant_id=tenant_id,
        )
    )


async def _notify(
    db: AsyncSession,
    recipient_id: UUID,
    title: str,
    message: str,
    *,
    entity_type: str,
    entity_id: UUID,
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


def _soft_risk_level(risk_justification: Optional[str]) -> Optional[str]:
    """Best-effort risk classification from the request's free-text
    justification -- there is no structured risk field on SupplierRequest yet
    (that's the Supplier Risk module, not built). Mirrors the keyword
    heuristic services/supplier_workflow.py already uses for compliance
    routing, extended to a 4-band scale."""
    text = (risk_justification or "").strip().lower()
    if not text:
        return None
    if "critical" in text:
        return "critical"
    if "high" in text:
        return "high"
    if "medium" in text or "moderate" in text:
        return "medium"
    return "low"


async def _resolve_templates(
    db: AsyncSession,
    module_codes: list[str],
    tenant_id: Optional[UUID],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for code in module_codes:
        module = MODULE_CODE_TO_TEMPLATE.get(code, f"supplier_registration_{code}")
        tmpl = await get_effective_template(db, module, tenant_id=tenant_id)
        if tmpl is not None:
            out[code] = tmpl
    return out


async def _create_pending_registration_instance(
    db: AsyncSession,
    registration: SupplierRegistration,
    *,
    requestor_id: UUID,
    actor_id: UUID,
    tenant_id: Optional[UUID],
) -> WorkflowInstance:
    """WorkflowInstance wrapper so completion reuses /workflow/tasks complete API.

    Completable by the Creator (requestor) OR an SLP Admin (FS Section 6) --
    _create_approval_tasks ignores role_code entirely once an explicit
    `approvers` list is given, so any resolvable SLP_ADMIN ApproverSeed users
    must be merged into that list up front rather than relied on via role_code.
    """
    approver_ids: set[str] = {str(requestor_id)}
    try:
        from app.crud.approval import resolve_approvers_for_context

        for admin in await resolve_approvers_for_context(db, role_code="SLP_ADMIN", tenant_id=tenant_id):
            approver_ids.add(admin["user_id"])
    except Exception:
        # No SLP_ADMIN ApproverSeed configured yet -- the Creator alone is
        # still a valid completer per FS Section 6.
        pass

    steps = [
        {
            "name": "Pending Registration",
            "step_type": "approval",
            "approvers": sorted(approver_ids),
            "role_code": "SLP_ADMIN",
            "required_approvals": 1,
        }
    ]
    definition = WorkflowDefinition(
        name=f"Pending registration {registration.registration_number}",
        entity_type="supplier_registration_pending",
        description="Ephemeral pending-registration gate (MANUAL mode)",
        steps=steps,
        status="published",
        is_active=False,
        created_by=actor_id,
    )
    db.add(definition)
    await db.flush()
    instance = WorkflowInstance(
        definition_id=definition.id,
        entity_type="supplier_registration_pending",
        entity_id=registration.id,
        status="in_progress",
        current_step_index=0,
        context={
            "registration_id": str(registration.id),
            "tenant_id": str(tenant_id) if tenant_id else None,
        },
        started_by=actor_id,
    )
    db.add(instance)
    await db.flush()
    # Create the human task via the shared engine path
    from app.crud.workflow import _create_approval_tasks

    await _create_approval_tasks(db, instance, steps[0], step_index=0)
    return instance


async def _spawn_adhoc_tasks(
    db: AsyncSession,
    supplier_type: SupplierType,
    *,
    trigger: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID,
    tenant_id: Optional[UUID],
    context: dict | None = None,
) -> list[WorkflowInstance]:
    templates = supplier_type.ad_hoc_task_templates or []
    created: list[WorkflowInstance] = []
    for tmpl in templates:
        if tmpl.get("trigger") != trigger:
            continue
        role_code = tmpl.get("role_code") or "SLP_ADMIN"
        due_days = int(tmpl.get("due_days") or 5)
        task_type = tmpl.get("task_type") or "clarification"
        steps = [
            {
                "name": f"Ad-hoc: {task_type}",
                "step_type": "approval",
                "role_code": role_code,
                "required_approvals": 1,
            }
        ]
        definition = WorkflowDefinition(
            name=f"Ad-hoc {task_type} ({supplier_type.code})",
            entity_type="supplier_adhoc_task",
            description=f"Ad-hoc task from SupplierType {supplier_type.code}",
            steps=steps,
            status="published",
            is_active=False,
            created_by=actor_id,
        )
        db.add(definition)
        await db.flush()
        instance = WorkflowInstance(
            definition_id=definition.id,
            entity_type="supplier_adhoc_task",
            entity_id=entity_id,
            status="in_progress",
            current_step_index=0,
            context={
                **(context or {}),
                "task_type": task_type,
                "trigger": trigger,
                "due_at": (datetime.now(timezone.utc) + timedelta(days=due_days)).isoformat(),
                "tenant_id": str(tenant_id) if tenant_id else None,
            },
            started_by=actor_id,
        )
        db.add(instance)
        await db.flush()
        from app.crud.workflow import _create_approval_tasks

        await _create_approval_tasks(db, instance, steps[0], step_index=0)
        created.append(instance)
    return created


async def send_registration_workbook(
    db: AsyncSession,
    registration_id: UUID,
    *,
    actor_id: UUID,
    commit: bool = False,
) -> SupplierRegistration:
    registration = (
        await db.execute(select(SupplierRegistration).where(SupplierRegistration.id == registration_id))
    ).scalar_one()
    supplier_type = None
    if registration.supplier_type_id:
        supplier_type = (
            await db.execute(select(SupplierType).where(SupplierType.id == registration.supplier_type_id))
        ).scalar_one_or_none()

    module_codes = list(supplier_type.required_questionnaire_modules or []) if supplier_type else []
    templates = await _resolve_templates(db, module_codes, registration.tenant_id)
    type_code = supplier_type.code if supplier_type else "UNKNOWN"

    xlsx_bytes, structure_hash = generate_registration_workbook(
        registration,
        type_code,
        templates,
        template_version=TEMPLATE_VERSION,
        questionnaire_version=QUESTIONNAIRE_VERSION,
    )
    key = file_storage.build_key(registration.id, "sent")
    await file_storage.save_bytes(key, xlsx_bytes)

    sla_days = 14
    if supplier_type and supplier_type.notification_rule:
        sla_days = int(supplier_type.notification_rule.get("sla_days") or 14)

    now = datetime.now(timezone.utc)
    registration.sent_workbook_path = key
    registration.structure_hash = structure_hash
    registration.template_version = TEMPLATE_VERSION
    registration.questionnaire_version = QUESTIONNAIRE_VERSION
    registration.workbook_sent_at = now
    registration.sla_due_at = now + timedelta(days=sla_days) if sla_days else None
    registration.status = "sent"
    registration.lifecycle_status = "registration_sent"

    # Notify requestor + SLP Admins (FS Section 11: "Registration invitation sent").
    recipients: set[UUID] = {registration.submitted_by}
    try:
        from app.crud.approval import resolve_approvers_for_context

        for admin in await resolve_approvers_for_context(db, role_code="SLP_ADMIN", tenant_id=registration.tenant_id):
            recipients.add(UUID(admin["user_id"]))
    except Exception:
        pass
    for recipient_id in recipients:
        await _notify(
            db,
            recipient_id,
            "Registration invitation sent",
            f"Excel registration workbook sent for {registration.registration_number}.",
            entity_type="supplier_registration",
            entity_id=registration.id,
        )
    _audit(
        db,
        entity_type="supplier_registration",
        entity_id=registration.id,
        actor_id=actor_id,
        action="registration:sent",
        details={"structure_hash": structure_hash, "modules": module_codes},
        tenant_id=registration.tenant_id,
    )
    if commit:
        await db.commit()
        await db.refresh(registration)
    else:
        await db.flush()
    return registration


async def _get_or_create_registration(
    db: AsyncSession,
    request: SupplierRequest,
    supplier: Supplier,
    supplier_type: Optional[SupplierType],
    *,
    status: str,
) -> tuple[SupplierRegistration, bool]:
    """Returns (registration, created). A prior partial run (e.g. workflow
    completion retried after a crash before commit) must not fan out a second
    SupplierRegistration + workbook + WorkflowInstance for the same request --
    supplier_request_id is unique per request in practice, so reuse it."""
    existing = (
        await db.execute(
            select(SupplierRegistration).where(SupplierRegistration.supplier_request_id == request.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    from app.crud.supplier_registration import generate_registration_number

    reg = SupplierRegistration(
        registration_number=generate_registration_number(),
        company_name=supplier.name,
        legal_name=supplier.legal_name or supplier.name,
        primary_contact_name=supplier.contact_email or "TBD",
        primary_contact_email=supplier.contact_email or "pending@example.com",
        address_line1="TBD",
        city="TBD",
        postal_code="00000",
        country=(request.preferred_region or "US")[:2].upper()
        if request.preferred_region and len(request.preferred_region) >= 2
        else "US",
        submitted_by=request.requestor_id,
        supplier_id=supplier.id,
        supplier_type_id=supplier_type.id if supplier_type else None,
        supplier_request_id=request.id,
        registration_mode=supplier_type.registration_mode if supplier_type else "manual",
        status=status,
        lifecycle_status=status,
        approval_status="pending",
        tenant_id=request.tenant_id,
    )
    # Contact name must be non-empty string — use request title as placeholder
    reg.primary_contact_name = request.title[:255] or "Pending"
    db.add(reg)
    await db.flush()
    return reg, True


async def on_supplier_request_approved(
    db: AsyncSession,
    supplier_request_id: UUID,
    *,
    actor_id: UUID,
    commit: bool = False,
) -> dict[str, Any]:
    """FS 5.2 steps 5-6: create Supplier, then branch on registration_mode."""
    request = (
        await db.execute(select(SupplierRequest).where(SupplierRequest.id == supplier_request_id))
    ).scalar_one_or_none()
    if request is None:
        return {"ok": False, "reason": "request_not_found"}

    request.approval_status = "approved"
    request.status = "approved"
    request.lifecycle_status = "approved"

    supplier_type = None
    if request.supplier_type_id:
        supplier_type = (
            await db.execute(select(SupplierType).where(SupplierType.id == request.supplier_type_id))
        ).scalar_one_or_none()

    mode = (supplier_type.registration_mode if supplier_type else "manual") or "manual"
    mode = mode.lower()

    if request.supplier_id:
        supplier = (
            await db.execute(select(Supplier).where(Supplier.id == request.supplier_id))
        ).scalar_one()
    else:
        supplier = Supplier(
            name=request.suggested_supplier_name or request.title,
            description=request.business_justification,
            diversity_classifications="required" if request.diversity_required else None,
            current_risk_level=_soft_risk_level(request.risk_justification),
            created_by=request.requestor_id,
            is_active=(mode == "none"),
            lifecycle_status="active" if mode == "none" else "pending_registration",
        )
        db.add(supplier)
        await db.flush()
        request.supplier_id = supplier.id
        _audit(
            db,
            entity_type="supplier",
            entity_id=supplier.id,
            actor_id=actor_id,
            action="supplier:created",
            details={
                "supplier_request_id": str(request.id),
                "registration_mode": mode,
                "supplier_type": supplier_type.code if supplier_type else None,
            },
            tenant_id=request.tenant_id,
        )
        await _notify(
            db,
            request.requestor_id,
            "Supplier created",
            f"Supplier '{supplier.name}' created from request '{request.title}'.",
            entity_type="supplier",
            entity_id=supplier.id,
        )

    result: dict[str, Any] = {
        "ok": True,
        "supplier_id": str(supplier.id),
        "registration_mode": mode,
        "registration_id": None,
    }

    if mode == "none":
        supplier.is_active = True
        supplier.lifecycle_status = "active"
        request.lifecycle_status = "completed"
        _audit(
            db,
            entity_type="supplier_request",
            entity_id=request.id,
            actor_id=actor_id,
            action="registration:skipped",
            details={"reason": "registration_mode=none"},
            tenant_id=request.tenant_id,
        )
    elif mode == "auto":
        registration, created = await _get_or_create_registration(
            db, request, supplier, supplier_type, status="pending_registration"
        )
        result["registration_id"] = str(registration.id)
        if created:
            await send_registration_workbook(db, registration.id, actor_id=actor_id, commit=False)
            request.lifecycle_status = "registration_sent"
            if supplier_type:
                await _spawn_adhoc_tasks(
                    db,
                    supplier_type,
                    trigger="on_request_approval",
                    entity_type="supplier_registration",
                    entity_id=registration.id,
                    actor_id=actor_id,
                    tenant_id=request.tenant_id,
                )
    else:  # manual
        registration, created = await _get_or_create_registration(
            db, request, supplier, supplier_type, status="pending_registration"
        )
        result["registration_id"] = str(registration.id)
        if created:
            await _create_pending_registration_instance(
                db,
                registration,
                requestor_id=request.requestor_id,
                actor_id=actor_id,
                tenant_id=request.tenant_id,
            )
            await _notify(
                db,
                request.requestor_id,
                "Registration pending",
                f"Manual registration ready to send for {registration.registration_number}.",
                entity_type="supplier_registration",
                entity_id=registration.id,
            )
            _audit(
                db,
                entity_type="supplier_registration",
                entity_id=registration.id,
                actor_id=actor_id,
                action="registration:pending",
                details={"mode": "manual"},
                tenant_id=request.tenant_id,
            )
            request.lifecycle_status = "registration_pending"
            if supplier_type:
                await _spawn_adhoc_tasks(
                    db,
                    supplier_type,
                    trigger="on_request_approval",
                    entity_type="supplier_registration",
                    entity_id=registration.id,
                    actor_id=actor_id,
                    tenant_id=request.tenant_id,
                )

    if commit:
        await db.commit()
    else:
        await db.flush()
    return result


async def apply_import_result(
    db: AsyncSession,
    registration: SupplierRegistration,
    import_result: Any,
    *,
    actor_id: UUID,
    returned_path: str,
    commit: bool = False,
) -> SupplierRegistration:
    """Persist a successful Excel import: TemplateResponses, scores, qualification."""
    from app.models.template import TemplateResponse

    registration.returned_workbook_path = returned_path
    registration.workbook_returned_at = datetime.now(timezone.utc)

    supplier_type = None
    if registration.supplier_type_id:
        supplier_type = (
            await db.execute(select(SupplierType).where(SupplierType.id == registration.supplier_type_id))
        ).scalar_one_or_none()

    info = import_result.supplier_info or {}
    if info.get("LegalName"):
        registration.legal_name = info["LegalName"]
        registration.company_name = info["LegalName"]
    if info.get("Country"):
        registration.country = info["Country"]
    if info.get("TaxID"):
        registration.tax_id = info["TaxID"]
    if info.get("BankAccountNumber"):
        registration.bank_account_number = info["BankAccountNumber"]
    if info.get("BankRoutingNumber"):
        registration.bank_routing_number = info["BankRoutingNumber"]
    if info.get("ContactName"):
        registration.primary_contact_name = info["ContactName"]
    if info.get("ContactEmail"):
        registration.primary_contact_email = info["ContactEmail"]
    if registration.bank_account_number or registration.bank_routing_number:
        registration.banking_info = (
            f"{registration.bank_account_number or ''} / {registration.bank_routing_number or ''}"
        ).strip(" /")

    module_codes = list(supplier_type.required_questionnaire_modules or []) if supplier_type else []
    templates = await _resolve_templates(db, module_codes, registration.tenant_id)
    module_scores: dict[str, dict] = {}
    total_weight = Decimal("0")
    weighted = Decimal("0")
    compliance_flags = 0

    for code, answers in (import_result.answers_by_module or {}).items():
        template = templates.get(code)
        if template is None:
            continue
        existing = (
            await db.execute(
                select(TemplateResponse).where(
                    TemplateResponse.entity_type == "supplier_registration",
                    TemplateResponse.entity_id == registration.id,
                    TemplateResponse.template_id == template.id,
                )
            )
        ).scalar_one_or_none()
        score, grade = score_response(template, answers)
        if existing is None:
            db.add(
                TemplateResponse(
                    template_id=template.id,
                    entity_type="supplier_registration",
                    entity_id=registration.id,
                    answers=answers,
                    computed_score=score,
                    computed_grade=grade,
                    submitted_by=actor_id,
                    submitted_at=datetime.now(timezone.utc),
                    tenant_id=registration.tenant_id,
                )
            )
        else:
            existing.answers = answers
            existing.computed_score = score
            existing.computed_grade = grade
            existing.submitted_by = actor_id
            existing.submitted_at = datetime.now(timezone.utc)
        module_scores[code] = {
            "score": float(score) if score is not None else None,
            "grade": grade,
        }
        if score is not None:
            total_weight += Decimal("1")
            weighted += score
        # Simple compliance flag: mandatory "no" on sanctions/code questions
        if answers.get("sanctions_screening_clear") in ("no", False, "No"):
            compliance_flags += 1
        if answers.get("code_of_conduct_accepted") in ("no", False, "No"):
            compliance_flags += 1

    if total_weight > 0:
        aggregate = (weighted / total_weight).quantize(Decimal("0.01"))
        # Aggregate grade uses FS bands (registration context)
        from app.services.template_engine import FS_REGISTRATION_GRADE_BANDS, grade_for_score

        registration.total_score = aggregate
        registration.grade = grade_for_score(aggregate, bands=FS_REGISTRATION_GRADE_BANDS)
    registration.module_scores = module_scores

    ctx = {
        "total_score": float(registration.total_score) if registration.total_score is not None else 0,
        "grade": registration.grade,
        "compliance_flags": compliance_flags,
    }
    qualified = True
    if supplier_type and supplier_type.qualification_rule:
        qualified = evaluate_visibility(supplier_type.qualification_rule, ctx)
    registration.qualification_status = "qualified" if qualified else "not_qualified"

    preferred = False
    if supplier_type and supplier_type.preferred_supplier_rule:
        preferred = evaluate_visibility(supplier_type.preferred_supplier_rule, ctx)
    registration.preferred_supplier_flag = preferred

    registration.status = "imported"
    registration.lifecycle_status = "registration_completed" if qualified else "registration_failed_qualification"
    registration.approval_status = "approved" if qualified else "pending"

    if registration.supplier_id and qualified:
        supplier = (
            await db.execute(select(Supplier).where(Supplier.id == registration.supplier_id))
        ).scalar_one_or_none()
        if supplier is not None:
            supplier.is_active = True
            supplier.lifecycle_status = "active"
            if registration.legal_name:
                supplier.legal_name = registration.legal_name
            if registration.tax_id:
                supplier.tax_id = registration.tax_id
            if registration.primary_contact_email:
                supplier.contact_email = registration.primary_contact_email

    await _notify(
        db,
        registration.submitted_by,
        "Registration completed",
        f"{registration.registration_number} imported — grade {registration.grade}, "
        f"qualification={registration.qualification_status}.",
        entity_type="supplier_registration",
        entity_id=registration.id,
    )
    _audit(
        db,
        entity_type="supplier_registration",
        entity_id=registration.id,
        actor_id=actor_id,
        action="registration:imported",
        details={
            "total_score": str(registration.total_score),
            "grade": registration.grade,
            "qualification_status": registration.qualification_status,
        },
        tenant_id=registration.tenant_id,
    )

    if supplier_type:
        await _spawn_adhoc_tasks(
            db,
            supplier_type,
            trigger="on_import",
            entity_type="supplier_registration",
            entity_id=registration.id,
            actor_id=actor_id,
            tenant_id=registration.tenant_id,
        )
        await _spawn_adhoc_tasks(
            db,
            supplier_type,
            trigger="on_qualification",
            entity_type="supplier_registration",
            entity_id=registration.id,
            actor_id=actor_id,
            tenant_id=registration.tenant_id,
            context={"qualification_status": registration.qualification_status},
        )

    if commit:
        await db.commit()
        await db.refresh(registration)
    else:
        await db.flush()
    return registration
