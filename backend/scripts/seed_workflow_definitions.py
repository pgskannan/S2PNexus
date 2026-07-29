import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import db_manager
from app.models.workflow import WorkflowDefinition
from app.schemas.workflow import WorkflowDefinitionCreate
from app.crud.workflow import create_workflow_definition


async def seed_workflow_definitions() -> None:
    async with db_manager.session_factory() as session:
        existing = await session.execute(
            __import__("sqlalchemy").select(WorkflowDefinition.entity_type).where(WorkflowDefinition.entity_type.in_( ["requisition", "purchase_order", "goods_receipt", "invoice_exception"] ))
        )
        existing_types = {row[0] for row in existing.fetchall()}

        definitions = [
            (
                "Requisition approval",
                "requisition",
                "Route requisition approvals through the workflow engine.",
                [
                    {
                        "name": "Initial review",
                        "step_type": "approval",
                        "approvers": [],
                        "required_approvals": 1,
                    },
                ],
            ),
            (
                "Purchase order approval",
                "purchase_order",
                "Route PO approvals through the workflow engine.",
                [
                    {
                        "name": "Finance review",
                        "step_type": "approval",
                        "approvers": [],
                        "required_approvals": 1,
                    },
                ],
            ),
            (
                "Goods receipt exception review",
                "goods_receipt",
                "Route goods receipt exceptions through the workflow engine.",
                [
                    {
                        "name": "Exception review",
                        "step_type": "approval",
                        "approvers": [],
                        "required_approvals": 1,
                    },
                ],
            ),
            (
                "Invoice exception review",
                "invoice_exception",
                "Route invoice matching exceptions through the workflow engine.",
                [
                    {
                        "name": "AP review",
                        "step_type": "approval",
                        "approvers": [],
                        "required_approvals": 1,
                    },
                ],
            ),
        ]

        for name, entity_type, description, steps in definitions:
            if entity_type in existing_types:
                continue
            payload = WorkflowDefinitionCreate(
                name=name,
                entity_type=entity_type,
                description=description,
                steps=steps,
                is_active=True,
            )
            await create_workflow_definition(session, payload, created_by=uuid4())

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_workflow_definitions())
