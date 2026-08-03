"""CRUD for the Universal Template Framework (Phase 1).

Template *authoring* is deliberately script/seed-driven in this batch (no
designer UI, per docs/FABLE5_TEMPLATE_AND_PREFERRED_SUPPLIER_PROMPT.md) --
this module covers the runtime paths: resolving the effective template,
upserting a response for an entity, and submitting (validate + score).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import TemplateDefinition, TemplateResponse
from app.services.template_engine import (
    get_effective_template,
    score_response,
    validate_mandatory,
)


class TemplateValidationError(ValueError):
    """Raised on submit when visible mandatory questions are unanswered."""

    def __init__(self, missing_keys: list[str]):
        self.missing_keys = missing_keys
        super().__init__(f"Missing mandatory answers: {', '.join(missing_keys)}")


async def get_response_for_entity(
    db: AsyncSession,
    entity_type: str,
    entity_id: UUID,
    tenant_id: Optional[UUID] = None,
) -> Optional[TemplateResponse]:
    """Tenant-scoped lookup. With a tenant_id, matches that tenant's rows OR
    untenanted rows (tenant_id IS NULL, e.g. backfilled before tenancy) --
    never another tenant's. With tenant_id=None, only untenanted rows match;
    there is deliberately no way to read across tenants from here."""
    query = select(TemplateResponse).where(
        TemplateResponse.entity_type == entity_type,
        TemplateResponse.entity_id == entity_id,
    )
    if tenant_id is not None:
        query = query.where(
            (TemplateResponse.tenant_id == tenant_id) | (TemplateResponse.tenant_id.is_(None))
        )
    else:
        query = query.where(TemplateResponse.tenant_id.is_(None))
    result = await db.execute(query.order_by(TemplateResponse.created_at.desc()).limit(1))
    return result.scalar_one_or_none()


async def upsert_template_response(
    db: AsyncSession,
    *,
    module: str,
    entity_type: str,
    entity_id: UUID,
    answers: dict[str, Any],
    submitted_by: Optional[UUID] = None,
    tenant_id: Optional[UUID] = None,
    submit: bool = False,
    commit: bool = True,
) -> Optional[TemplateResponse]:
    """Create or update the TemplateResponse for an entity.

    Resolves the effective template for `module`/`tenant_id`. Returns None if
    no template is published for the module -- callers fall back to legacy
    behavior (same zero-regression contract as the workflow integrations).

    With submit=True, visible mandatory questions are enforced
    (TemplateValidationError lists the missing keys) and the composite
    score/grade is computed and stored.

    commit=False lets callers that manage their own transaction (e.g.
    supplier-request creation, which must not half-commit) flush instead.
    """
    template = await get_effective_template(db, module, tenant_id)
    if template is None:
        return None

    response = await get_response_for_entity(db, entity_type, entity_id, tenant_id=tenant_id)
    if response is None:
        response = TemplateResponse(
            template_id=template.id,
            entity_type=entity_type,
            entity_id=entity_id,
            answers={},
            tenant_id=tenant_id,
        )
        db.add(response)

    merged = dict(response.answers or {})
    merged.update(answers or {})
    response.answers = merged
    if submitted_by is not None:
        response.submitted_by = submitted_by

    if submit:
        missing = validate_mandatory(template, merged)
        if missing:
            raise TemplateValidationError(missing)
        score, grade = score_response(template, merged)
        response.computed_score = score
        response.computed_grade = grade
        response.submitted_at = datetime.now(timezone.utc)

    if commit:
        await db.commit()
        await db.refresh(response)
    else:
        await db.flush()
    return response


async def get_template_definition(db: AsyncSession, template_id: UUID) -> Optional[TemplateDefinition]:
    result = await db.execute(select(TemplateDefinition).where(TemplateDefinition.id == template_id))
    return result.scalar_one_or_none()
