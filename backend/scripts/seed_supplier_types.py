#!/usr/bin/env python3
"""Seed the four Supplier Types from FS Section 17 (configuration matrix).

Section 17 in docs/SUPPLIER_TYPE_REGISTRATION_FS.md was a stub at paste time;
the matrix below is the canonical capture of the four types named in the
implementation prompt (STD_VENDOR AUTO, CONSULTANT MANUAL, ONE_TIME_VENDOR
NONE, HIGH_RISK_VENDOR MANUAL) with approval/module/task defaults derived
from FS Sections 4, 8, 10, and 17's role list.

USAGE
-----
    cd backend
    python -m scripts.seed_supplier_types

Safe to re-run: upsert-by-(tenant NULL, code) via upsert_supplier_type_by_code.
"""

from __future__ import annotations

import asyncio
import pkgutil

import app.models as _models_pkg  # noqa: F401,E402

for _model_module in pkgutil.iter_modules(_models_pkg.__path__):
    __import__(f"app.models.{_model_module.name}")

from app.crud.supplier_type import upsert_supplier_type_by_code
from app.database.database import db_manager
from app.schemas.supplier_type import SupplierTypeCreate

# FS Section 17 matrix (canonical for this batch). Changing a type's
# registration_mode here (or in the admin UI) changes next-request behavior
# without a code change — that is the Definition of Done for configurability.
SUPPLIER_TYPES: list[SupplierTypeCreate] = [
    SupplierTypeCreate(
        code="STD_VENDOR",
        name="Standard Vendor",
        registration_mode="auto",
        registration_method="excel_only",
        required_questionnaire_modules=["core", "tax", "bank", "compliance"],
        qualification_rule={"field": "total_score", "op": "gte", "value": 50},
        preferred_supplier_rule={
            "all": [
                {"field": "grade", "op": "eq", "value": "A"},
                {"field": "compliance_flags", "op": "eq", "value": 0},
            ]
        },
        ad_hoc_task_templates=[
            {"task_type": "compliance_review", "trigger": "on_import", "role_code": "COMPLIANCE", "due_days": 5},
        ],
        notification_rule={"sla_days": 14, "reminder_at_days": [7, 11], "escalation_at_days": 14},
        approval_workflow_config=["BU_MANAGER", "PROC_HEAD"],
        description="Default vendor path: Excel registration sent automatically on request approval.",
        is_active=True,
    ),
    SupplierTypeCreate(
        code="CONSULTANT",
        name="Consultant",
        registration_mode="manual",
        registration_method="excel_only",
        required_questionnaire_modules=["core", "tax", "compliance", "infosec"],
        qualification_rule={"field": "total_score", "op": "gte", "value": 50},
        preferred_supplier_rule={"field": "grade", "op": "in", "value": ["A", "B"]},
        ad_hoc_task_templates=[
            {"task_type": "legal_review", "trigger": "on_request_approval", "role_code": "LEGAL", "due_days": 7},
            {"task_type": "clarification", "trigger": "on_import", "role_code": "SLP_ADMIN", "due_days": 3},
        ],
        notification_rule={"sla_days": 21, "reminder_at_days": [10, 17], "escalation_at_days": 21},
        approval_workflow_config=["BU_MANAGER", "LEGAL", "PROC_HEAD"],
        description="Manual registration trigger by Creator or SLP Admin after supplier creation.",
        is_active=True,
    ),
    SupplierTypeCreate(
        code="ONE_TIME_VENDOR",
        name="One-Time Vendor",
        registration_mode="none",
        registration_method="excel_only",
        required_questionnaire_modules=[],
        qualification_rule=None,
        preferred_supplier_rule=None,
        ad_hoc_task_templates=[],
        notification_rule={"sla_days": 0, "reminder_at_days": [], "escalation_at_days": 0},
        approval_workflow_config=["BU_MANAGER"],
        description="No registration step; supplier marked active on request approval.",
        is_active=True,
    ),
    SupplierTypeCreate(
        code="HIGH_RISK_VENDOR",
        name="High-Risk Vendor",
        registration_mode="manual",
        registration_method="excel_only",
        required_questionnaire_modules=[
            "core",
            "tax",
            "bank",
            "compliance",
            "esg",
            "infosec",
            "financial",
        ],
        qualification_rule={
            "all": [
                {"field": "total_score", "op": "gte", "value": 75},
                {"field": "compliance_flags", "op": "eq", "value": 0},
            ]
        },
        preferred_supplier_rule={
            "all": [
                {"field": "grade", "op": "eq", "value": "A"},
                {"field": "compliance_flags", "op": "eq", "value": 0},
            ]
        },
        ad_hoc_task_templates=[
            {"task_type": "risk_review", "trigger": "on_request_approval", "role_code": "RISK", "due_days": 5},
            {"task_type": "compliance_review", "trigger": "on_import", "role_code": "COMPLIANCE", "due_days": 5},
            {"task_type": "legal_review", "trigger": "on_qualification", "role_code": "LEGAL", "due_days": 7},
            {"task_type": "category_manager_review", "trigger": "on_qualification", "role_code": "CATEGORY_MGR", "due_days": 7},
        ],
        notification_rule={"sla_days": 30, "reminder_at_days": [14, 21, 27], "escalation_at_days": 30},
        approval_workflow_config=["BU_MANAGER", "RISK", "COMPLIANCE", "LEGAL", "PROC_HEAD"],
        description="Full questionnaire + multi-role approval; registration manually triggered.",
        is_active=True,
    ),
]


async def seed_supplier_types() -> list[str]:
    codes: list[str] = []
    async with db_manager.session_factory() as session:
        for payload in SUPPLIER_TYPES:
            row = await upsert_supplier_type_by_code(session, payload, commit=False)
            codes.append(row.code)
        await session.commit()
    return codes


async def main() -> None:
    codes = await seed_supplier_types()
    print(f"Seeded {len(codes)} supplier types: {', '.join(codes)}")


if __name__ == "__main__":
    asyncio.run(main())
