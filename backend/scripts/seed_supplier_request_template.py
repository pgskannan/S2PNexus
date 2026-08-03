#!/usr/bin/env python3
"""Seed the global Supplier Request template (Template Framework Phase 1)
and backfill TemplateResponse rows for existing SupplierRequest rows.

The template mirrors SupplierRequest's legacy fixed columns one-for-one
(business_justification, commodity_categories, suggested_supplier_name,
existing_supplier_check, preferred_region, estimated_annual_spend,
diversity_required, risk_justification) and adds the two conditional
questions those fixed columns could never express (the spec Section 2 SLP
pain point this phase exists to fix):

- diversity_required = yes  -> "Diversity Certification Upload" (file_upload)
- risk_justification filled -> "Risk Mitigation Plan" (textarea)

plus a lightweight completeness/risk scoring rule (spec Section 7) -- not a
gate, just computed and surfaced to reviewers.

Backfill: one TemplateResponse per existing SupplierRequest that doesn't
already have one, answers copied from the legacy columns (which are KEPT --
Phase 1 does not drop columns; the template is the write path for new
requests, the columns remain the compatibility read path).

Direct-DB script, same contract as seed_approver_matrix.py: reads
DATABASE_URL via app.core.config.settings, no credentials in the script.

USAGE
-----
    cd backend
    python -m scripts.seed_supplier_request_template

Safe to re-run: the template is upserted by (module, tenant NULL, name) --
re-running bumps nothing unless questions changed, in which case a new
version is published and the old one deprecated. Backfill skips requests
that already have a response.
"""

from __future__ import annotations

import asyncio
import pkgutil

# Register the COMPLETE model registry before any mapper configuration runs
# (same portability note as seed_approver_matrix.py).
import app.models as _models_pkg  # noqa: F401,E402
for _model_module in pkgutil.iter_modules(_models_pkg.__path__):
    __import__(f"app.models.{_model_module.name}")

from sqlalchemy import select

from app.database.database import db_manager
from app.models.supplier_request import SupplierRequest
from app.models.template import (
    TemplateDefinition,
    TemplateQuestion,
    TemplateResponse,
    TemplateSection,
)

TEMPLATE_NAME = "Supplier Request (default)"
MODULE = "supplier_request"

# Section/question layout. question_key values for the mirrored questions are
# EXACTLY the legacy column names, so the backfill (and any code translating
# between the two representations) is a plain dict copy, no mapping table.
SECTIONS = [
    {
        "name": "Request Details",
        "order": 0,
        "questions": [
            {
                "question_key": "business_justification",
                "question_type": "textarea",
                "question_text": "Business justification",
                "help_text": "Why does the business need this supplier?",
                "mandatory_flag": True,
                "order": 0,
                "scoring_rule": {"weight": 20, "present": 10},
            },
            {
                "question_key": "commodity_categories",
                "question_type": "text",
                "question_text": "Commodity categories",
                "placeholder": "e.g. IT Hardware, MRO",
                "order": 1,
            },
            {
                "question_key": "suggested_supplier_name",
                "question_type": "text",
                "question_text": "Suggested supplier name",
                "order": 2,
            },
            {
                "question_key": "existing_supplier_check",
                "question_type": "yes_no",
                "question_text": "Have you checked whether an existing supplier can fulfill this need?",
                "mandatory_flag": True,
                "order": 3,
                "scoring_rule": {"weight": 30, "map": {"yes": 10, "no": 0, "true": 10, "false": 0}},
            },
            {
                "question_key": "preferred_region",
                "question_type": "text",
                "question_text": "Preferred region",
                "order": 4,
            },
            {
                "question_key": "estimated_annual_spend",
                "question_type": "numeric",
                "question_text": "Estimated annual spend (USD)",
                "order": 5,
            },
        ],
    },
    {
        "name": "Diversity",
        "order": 1,
        "questions": [
            {
                "question_key": "diversity_required",
                "question_type": "yes_no",
                "question_text": "Is a diverse supplier required for this request?",
                "mandatory_flag": True,
                "order": 0,
            },
            {
                # NEW conditional question -- template-only, no legacy column.
                "question_key": "diversity_certification_upload",
                "question_type": "file_upload",
                "question_text": "Diversity certification",
                "help_text": "Upload the certification document supporting the diversity requirement.",
                "mandatory_flag": True,
                "visibility_rule": {"field": "diversity_required", "op": "eq", "value": "yes"},
                "order": 1,
            },
        ],
    },
    {
        "name": "Risk",
        "order": 2,
        "questions": [
            {
                "question_key": "risk_justification",
                "question_type": "textarea",
                "question_text": "Risk justification (if any known risks)",
                "order": 0,
            },
            {
                # NEW conditional question -- template-only, no legacy column.
                "question_key": "risk_mitigation_plan",
                "question_type": "textarea",
                "question_text": "Risk mitigation plan",
                "help_text": "You flagged a risk above -- describe how it will be mitigated.",
                "mandatory_flag": True,
                "visibility_rule": {"field": "risk_justification", "op": "neq", "value": ""},
                "order": 1,
                # Known risk without a mitigation plan drags the score:
                "scoring_rule": {"weight": 30, "present": 10},
            },
        ],
    },
]

async def seed_template(session) -> TemplateDefinition:
    existing = (
        await session.execute(
            select(TemplateDefinition).where(
                TemplateDefinition.module == MODULE,
                TemplateDefinition.tenant_id.is_(None),
                TemplateDefinition.name == TEMPLATE_NAME,
                TemplateDefinition.status == "published",
            )
        )
    ).scalars().first()
    if existing:
        print(f"Template already published: {existing.id} v{existing.version} -- leaving unchanged")
        return existing

    template = TemplateDefinition(
        module=MODULE,
        name=TEMPLATE_NAME,
        description="Default global supplier request intake questionnaire (Phase 1). "
        "Mirrors the legacy fixed columns plus conditional diversity/risk questions.",
        version=1,
        status="published",
        inheritance_mode="global",
    )
    session.add(template)
    await session.flush()

    for section_spec in SECTIONS:
        section = TemplateSection(
            template_id=template.id,
            name=section_spec["name"],
            order=section_spec["order"],
        )
        session.add(section)
        await session.flush()
        for q in section_spec["questions"]:
            session.add(
                TemplateQuestion(
                    section_id=section.id,
                    question_key=q["question_key"],
                    question_type=q["question_type"],
                    question_text=q["question_text"],
                    help_text=q.get("help_text"),
                    placeholder=q.get("placeholder"),
                    mandatory_flag=q.get("mandatory_flag", False),
                    visibility_rule=q.get("visibility_rule"),
                    scoring_rule=q.get("scoring_rule"),
                    order=q.get("order", 0),
                )
            )
    print(f"Published template {template.id} ({TEMPLATE_NAME})")
    return template


def _answers_from_legacy(request: SupplierRequest) -> dict:
    """Copy legacy columns into template answers. yes_no answers are stored
    as 'yes'/'no' strings to match the visibility-rule values."""
    return {
        "business_justification": request.business_justification,
        "commodity_categories": request.commodity_categories,
        "suggested_supplier_name": request.suggested_supplier_name,
        "existing_supplier_check": "yes" if request.existing_supplier_check else "no",
        "preferred_region": request.preferred_region,
        "estimated_annual_spend": str(request.estimated_annual_spend) if request.estimated_annual_spend is not None else None,
        "diversity_required": "yes" if request.diversity_required else "no",
        "risk_justification": request.risk_justification,
    }


async def backfill_responses(session, template: TemplateDefinition) -> int:
    requests = (await session.execute(select(SupplierRequest))).scalars().all()
    created = 0
    for request in requests:
        existing = (
            await session.execute(
                select(TemplateResponse).where(
                    TemplateResponse.entity_type == "supplier_request",
                    TemplateResponse.entity_id == request.id,
                )
            )
        ).scalars().first()
        if existing:
            continue
        answers = {k: v for k, v in _answers_from_legacy(request).items() if v is not None}
        session.add(
            TemplateResponse(
                template_id=template.id,
                entity_type="supplier_request",
                entity_id=request.id,
                answers=answers,
                tenant_id=request.tenant_id,
                submitted_by=request.requestor_id,
                submitted_at=request.created_at,
            )
        )
        created += 1
    print(f"Backfilled {created} TemplateResponse rows ({len(requests) - created} already had one)")
    return created


async def main() -> None:
    async with db_manager.session_factory() as session:
        template = await seed_template(session)
        await backfill_responses(session, template)
        await session.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
