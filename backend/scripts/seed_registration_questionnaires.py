#!/usr/bin/env python3
"""Seed FS Section 8 questionnaire modules as TemplateDefinitions.

One published global template per supplier_registration_* module so
SupplierType.required_questionnaire_modules can resolve them independently
via get_effective_template() (one active template per module).

TemplateResponse shape used by Excel import (Phase 4):
  entity_type = "supplier_registration"
  entity_id   = SupplierRegistration.id
  one TemplateResponse row PER module (template.module distinguishes them).

USAGE
-----
    cd backend
    python -m scripts.seed_registration_questionnaires
"""

from __future__ import annotations

import asyncio
import pkgutil

import app.models as _models_pkg  # noqa: F401,E402

for _model_module in pkgutil.iter_modules(_models_pkg.__path__):
    __import__(f"app.models.{_model_module.name}")

from sqlalchemy import select

from app.database.database import db_manager
from app.models.template import TemplateDefinition, TemplateQuestion, TemplateSection

# module_code -> (TEMPLATE_MODULES name, display, questions)
MODULES: dict[str, tuple[str, str, list[dict]]] = {
    "core": (
        "supplier_registration_core",
        "Core Company Information",
        [
            {
                "question_key": "years_in_business",
                "question_type": "numeric",
                "question_text": "Years in business",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 20, "threshold": 3, "above": 10, "below": 4},
            },
            {
                "question_key": "employee_count_band",
                "question_type": "dropdown",
                "question_text": "Employee count",
                "options": ["1-10", "11-50", "51-250", "251-1000", "1000+"],
                "mandatory_flag": True,
                "scoring_rule": {
                    "weight": 15,
                    "map": {"1-10": 4, "11-50": 6, "51-250": 8, "251-1000": 9, "1000+": 10},
                },
            },
            {
                "question_key": "primary_goods_services",
                "question_type": "textarea",
                "question_text": "Primary goods / services offered",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 25, "present": 10},
            },
            {
                "question_key": "publicly_traded",
                "question_type": "yes_no",
                "question_text": "Is the company publicly traded?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 10, "map": {"yes": 8, "no": 6}},
            },
        ],
    ),
    "tax": (
        "supplier_registration_tax",
        "Tax Information",
        [
            {
                "question_key": "tax_classification",
                "question_type": "dropdown",
                "question_text": "Tax classification",
                "options": ["Corporation", "LLC", "Partnership", "Sole Proprietor", "Non-profit"],
                "mandatory_flag": True,
                "scoring_rule": {"weight": 30, "present": 10},
            },
            {
                "question_key": "w9_available",
                "question_type": "yes_no",
                "question_text": "W-9 / tax form available on request?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 40, "map": {"yes": 10, "no": 0}},
            },
            {
                "question_key": "vat_registered",
                "question_type": "yes_no",
                "question_text": "VAT / GST registered (if applicable)?",
                "mandatory_flag": False,
                "scoring_rule": {"weight": 30, "map": {"yes": 10, "no": 5}},
            },
        ],
    ),
    "bank": (
        "supplier_registration_bank",
        "Banking & Payment",
        [
            {
                "question_key": "preferred_payment_method",
                "question_type": "dropdown",
                "question_text": "Preferred payment method",
                "options": ["ACH", "Wire", "Check", "Card"],
                "mandatory_flag": True,
                "scoring_rule": {"weight": 40, "present": 10},
            },
            {
                "question_key": "payment_terms_accepted",
                "question_type": "dropdown",
                "question_text": "Standard payment terms accepted",
                "options": ["Net 30", "Net 45", "Net 60", "Due on receipt"],
                "mandatory_flag": True,
                "scoring_rule": {
                    "weight": 40,
                    "map": {"Net 30": 10, "Net 45": 8, "Net 60": 6, "Due on receipt": 4},
                },
            },
            {
                "question_key": "bank_letter_available",
                "question_type": "yes_no",
                "question_text": "Bank verification letter available?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 20, "map": {"yes": 10, "no": 2}},
            },
        ],
    ),
    "compliance": (
        "supplier_registration_compliance",
        "Compliance",
        [
            {
                "question_key": "code_of_conduct_accepted",
                "question_type": "yes_no",
                "question_text": "Accept buyer Code of Conduct?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 40, "map": {"yes": 10, "no": 0}},
            },
            {
                "question_key": "sanctions_screening_clear",
                "question_type": "yes_no",
                "question_text": "Clear of sanctions / denied-party lists?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 40, "map": {"yes": 10, "no": 0}},
            },
            {
                "question_key": "anti_bribery_policy",
                "question_type": "yes_no",
                "question_text": "Anti-bribery / anti-corruption policy in place?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 20, "map": {"yes": 10, "no": 3}},
            },
        ],
    ),
    "esg": (
        "supplier_registration_esg",
        "ESG",
        [
            {
                "question_key": "esg_policy",
                "question_type": "yes_no",
                "question_text": "Documented ESG / sustainability policy?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 40, "map": {"yes": 10, "no": 2}},
            },
            {
                "question_key": "carbon_reporting",
                "question_type": "yes_no",
                "question_text": "Reports Scope 1/2 carbon emissions?",
                "mandatory_flag": False,
                "scoring_rule": {"weight": 30, "map": {"yes": 10, "no": 4}},
            },
            {
                "question_key": "diversity_program",
                "question_type": "yes_no",
                "question_text": "Supplier diversity program participant?",
                "mandatory_flag": False,
                "scoring_rule": {"weight": 30, "map": {"yes": 10, "no": 5}},
            },
        ],
    ),
    "infosec": (
        "supplier_registration_infosec",
        "Information Security",
        [
            {
                "question_key": "iso27001",
                "question_type": "yes_no",
                "question_text": "ISO 27001 (or equivalent) certified?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 40, "map": {"yes": 10, "no": 3}},
            },
            {
                "question_key": "data_breach_process",
                "question_type": "yes_no",
                "question_text": "Documented data-breach notification process?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 35, "map": {"yes": 10, "no": 2}},
            },
            {
                "question_key": "processes_pii",
                "question_type": "yes_no",
                "question_text": "Will process buyer PII / personal data?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 25, "map": {"yes": 6, "no": 10}},
            },
        ],
    ),
    "financial": (
        "supplier_registration_financial",
        "Financial Stability",
        [
            {
                "question_key": "audited_financials",
                "question_type": "yes_no",
                "question_text": "Audited financial statements available (last 2 years)?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 40, "map": {"yes": 10, "no": 2}},
            },
            {
                "question_key": "bankruptcy_5y",
                "question_type": "yes_no",
                "question_text": "Any bankruptcy / insolvency in last 5 years?",
                "mandatory_flag": True,
                "scoring_rule": {"weight": 40, "map": {"yes": 0, "no": 10}},
            },
            {
                "question_key": "revenue_band",
                "question_type": "dropdown",
                "question_text": "Annual revenue band (USD)",
                "options": ["<1M", "1M-10M", "10M-50M", "50M-250M", "250M+"],
                "mandatory_flag": True,
                "scoring_rule": {
                    "weight": 20,
                    "map": {"<1M": 3, "1M-10M": 5, "10M-50M": 7, "50M-250M": 9, "250M+": 10},
                },
            },
        ],
    ),
}


async def _upsert_module(session, module: str, name: str, questions: list[dict]) -> str:
    existing = (
        await session.execute(
            select(TemplateDefinition).where(
                TemplateDefinition.module == module,
                TemplateDefinition.tenant_id.is_(None),
                TemplateDefinition.name == name,
                TemplateDefinition.status == "published",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return f"kept:{module}"

    # Deprecate prior published for this module (global).
    prior = (
        await session.execute(
            select(TemplateDefinition).where(
                TemplateDefinition.module == module,
                TemplateDefinition.tenant_id.is_(None),
                TemplateDefinition.status == "published",
            )
        )
    ).scalars().all()
    for row in prior:
        row.status = "deprecated"

    definition = TemplateDefinition(
        tenant_id=None,
        module=module,
        name=name,
        description=f"FS Section 8 questionnaire module ({module})",
        version=1,
        status="published",
        inheritance_mode="global",
    )
    session.add(definition)
    await session.flush()

    section = TemplateSection(
        template_id=definition.id,
        name=name,
        order=0,
        mandatory_flag=True,
    )
    session.add(section)
    await session.flush()

    for idx, q in enumerate(questions):
        session.add(
            TemplateQuestion(
                section_id=section.id,
                question_key=q["question_key"],
                question_type=q["question_type"],
                question_text=q["question_text"],
                options=q.get("options"),
                mandatory_flag=q.get("mandatory_flag", False),
                scoring_rule=q.get("scoring_rule"),
                order=idx,
                editable_flag=True,
                visible_flag=True,
            )
        )
    return f"published:{module}"


async def seed_registration_questionnaires() -> list[str]:
    results: list[str] = []
    async with db_manager.session_factory() as session:
        for _code, (module, name, questions) in MODULES.items():
            results.append(await _upsert_module(session, module, name, questions))
        await session.commit()
    return results


async def main() -> None:
    results = await seed_registration_questionnaires()
    print("Seeded registration questionnaires:")
    for line in results:
        print(f"  {line}")


if __name__ == "__main__":
    asyncio.run(main())
