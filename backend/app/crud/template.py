"""CRUD for the Universal Template Framework (Phase 1).

Template *authoring* is deliberately script/seed-driven in this batch (no
designer UI, per docs/FABLE5_TEMPLATE_AND_PREFERRED_SUPPLIER_PROMPT.md) --
this module covers the runtime paths: resolving the effective template,
upserting a response for an entity, and submitting (validate + score).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import (
    TemplateDefinition,
    TemplateQuestion,
    TemplateResponse,
    TemplateSection,
)
from app.schemas.template import TemplateDefinitionCreate
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


# ---- Authoring (Template Admin UI, Phase 2) ----
#
# Everything above this line is the original Phase 1 runtime surface
# (deliberately read-only per this module's docstring). These functions add
# the write path the seed scripts used to be the only way to reach.
#
# Tenant scoping follows the same rule as gl_accounts/commodity CRUD:
# tenant_id is always derived server-side from the caller's session, never
# accepted from the request body, so a tenant admin can never write (or
# read-by-id) another tenant's row or the global (tenant_id NULL) template by
# guessing its id -- the same class of IDOR fixed earlier in the PO and
# commodity/address modules.


class TemplateStateError(ValueError):
    """Raised when an authoring action is attempted on a definition in the wrong status."""


def _tenant_or_global_filter(tenant_id: Optional[UUID]):
    if tenant_id is not None:
        return (TemplateDefinition.tenant_id == tenant_id) | (TemplateDefinition.tenant_id.is_(None))
    return TemplateDefinition.tenant_id.is_(None)


async def list_template_definitions(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    module: Optional[str] = None,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> list[TemplateDefinition]:
    """Admin list: this tenant's own definitions plus the global ones, mirroring
    get_effective_template's inheritance scope -- an admin should see what they
    can override, never another tenant's private templates."""
    query = select(TemplateDefinition).where(_tenant_or_global_filter(tenant_id))
    if module:
        query = query.where(TemplateDefinition.module == module)
    if status_filter:
        query = query.where(TemplateDefinition.status == status_filter)
    query = query.order_by(
        TemplateDefinition.module, TemplateDefinition.name, TemplateDefinition.version.desc()
    )
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all())


async def count_template_definitions(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    module: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> int:
    query = select(sa_func.count()).select_from(TemplateDefinition).where(_tenant_or_global_filter(tenant_id))
    if module:
        query = query.where(TemplateDefinition.module == module)
    if status_filter:
        query = query.where(TemplateDefinition.status == status_filter)
    result = await db.execute(query)
    return int(result.scalar_one())


async def get_template_definition_for_tenant(
    db: AsyncSession, template_id: UUID, *, tenant_id: Optional[UUID]
) -> Optional[TemplateDefinition]:
    """Same tenant-or-global scope as list_template_definitions, enforced per
    row so an admin can't fetch/edit/publish/delete another tenant's template
    by guessing its id."""
    definition = await get_template_definition(db, template_id)
    if definition is None:
        return None
    if definition.tenant_id is not None and definition.tenant_id != tenant_id:
        return None
    return definition


def _build_sections(sections_data) -> list[TemplateSection]:
    sections: list[TemplateSection] = []
    for section_data in sections_data:
        section = TemplateSection(
            name=section_data.name,
            order=section_data.order,
            visibility_rule=section_data.visibility_rule,
            mandatory_flag=section_data.mandatory_flag,
        )
        for q in section_data.questions:
            section.questions.append(
                TemplateQuestion(
                    question_key=q.question_key,
                    question_type=q.question_type,
                    question_text=q.question_text,
                    help_text=q.help_text,
                    placeholder=q.placeholder,
                    default_value=q.default_value,
                    options=q.options,
                    editable_flag=q.editable_flag,
                    visible_flag=q.visible_flag,
                    mandatory_flag=q.mandatory_flag,
                    visibility_rule=q.visibility_rule,
                    scoring_rule=q.scoring_rule,
                    parent_question_key=q.parent_question_key,
                    order=q.order,
                )
            )
        sections.append(section)
    return sections


async def create_template_definition(
    db: AsyncSession,
    data: TemplateDefinitionCreate,
    *,
    tenant_id: Optional[UUID],
    created_by: Optional[UUID],
) -> TemplateDefinition:
    """Creates a new draft. Version auto-increments within (tenant_id, module,
    name) -- a brand-new name starts at 1; authoring a new version of an
    existing name (e.g. "Edit" on a published definition, which the router
    routes through here rather than mutating the published row) picks up
    where the highest existing version for that scope left off."""
    result = await db.execute(
        select(sa_func.max(TemplateDefinition.version)).where(
            TemplateDefinition.tenant_id == tenant_id,
            TemplateDefinition.module == data.module,
            TemplateDefinition.name == data.name,
        )
    )
    next_version = (result.scalar_one_or_none() or 0) + 1

    definition = TemplateDefinition(
        tenant_id=tenant_id,
        module=data.module,
        name=data.name,
        description=data.description,
        version=next_version,
        status="draft",
        effective_date=data.effective_date,
        expiry_date=data.expiry_date,
        inheritance_mode=data.inheritance_mode,
        created_by=created_by,
        sections=_build_sections(data.sections),
    )
    db.add(definition)
    await db.commit()
    await db.refresh(definition)
    return definition


async def update_draft_template_definition(
    db: AsyncSession,
    template_id: UUID,
    data: TemplateDefinitionCreate,
    *,
    tenant_id: Optional[UUID],
) -> Optional[TemplateDefinition]:
    """In-place edit, draft only. A published/deprecated definition can't be
    edited here -- go through create_template_definition for a new version
    instead, so a live TemplateResponse never sees its questions change under
    it mid-flight."""
    definition = await get_template_definition_for_tenant(db, template_id, tenant_id=tenant_id)
    if definition is None:
        return None
    if definition.status != "draft":
        raise TemplateStateError(f"Cannot edit a {definition.status} template -- publish a new version instead")
    if data.module != definition.module:
        raise TemplateStateError("module cannot change on an existing template")

    definition.name = data.name
    definition.description = data.description
    definition.effective_date = data.effective_date
    definition.expiry_date = data.expiry_date
    definition.inheritance_mode = data.inheritance_mode

    # cascade="all, delete-orphan" on TemplateDefinition.sections (and
    # TemplateSection.questions) means clearing the list deletes the
    # orphaned rows -- safe here because a draft has never been published,
    # so no TemplateResponse can be pointing at these question rows yet.
    definition.sections.clear()
    await db.flush()
    for section in _build_sections(data.sections):
        section.template_id = definition.id
        definition.sections.append(section)

    await db.commit()
    await db.refresh(definition)
    return definition


async def publish_template_definition(
    db: AsyncSession,
    template_id: UUID,
    *,
    tenant_id: Optional[UUID],
    effective_date: Optional[date_type] = None,
) -> Optional[TemplateDefinition]:
    """Draft -> published, and deprecates whatever definition previously held
    "published" for the same (tenant_id, module, name) scope. At most one
    published version per scope at a time; get_effective_template's "highest
    published version wins" query would pick the new one anyway, but
    deprecating the old one keeps the admin list view honest."""
    definition = await get_template_definition_for_tenant(db, template_id, tenant_id=tenant_id)
    if definition is None:
        return None
    if definition.status != "draft":
        raise TemplateStateError(f"Cannot publish a {definition.status} template")
    if not definition.sections:
        raise TemplateStateError("Cannot publish a template with no sections")

    result = await db.execute(
        select(TemplateDefinition).where(
            TemplateDefinition.tenant_id == definition.tenant_id,
            TemplateDefinition.module == definition.module,
            TemplateDefinition.name == definition.name,
            TemplateDefinition.status == "published",
            TemplateDefinition.id != definition.id,
        )
    )
    for previous in result.scalars().all():
        previous.status = "deprecated"

    definition.status = "published"
    definition.effective_date = effective_date or definition.effective_date or date_type.today()
    await db.commit()
    await db.refresh(definition)
    return definition


async def delete_draft_template_definition(
    db: AsyncSession, template_id: UUID, *, tenant_id: Optional[UUID]
) -> bool:
    """Draft only -- published definitions are never deleted (TemplateResponse.
    template_id is an ON DELETE RESTRICT FK on purpose: a submitted response
    must always be able to re-render the template it was answered against)."""
    definition = await get_template_definition_for_tenant(db, template_id, tenant_id=tenant_id)
    if definition is None:
        return False
    if definition.status != "draft":
        raise TemplateStateError(f"Cannot delete a {definition.status} template")
    await db.delete(definition)
    await db.commit()
    return True
