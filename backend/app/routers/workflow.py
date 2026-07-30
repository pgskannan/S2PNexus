"""Workflow Automation router for S2PNexus (Sprint 2 ADR Phase 2F)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.workflow import (
    complete_task,
    create_workflow_definition,
    delete_workflow_definition,
    escalate_overdue_tasks,
    get_my_tasks,
    get_notifications,
    get_notifications_count,
    get_workflow_definition,
    get_workflow_definitions,
    get_workflow_definitions_count,
    get_workflow_instance,
    get_workflow_instances,
    get_workflow_instances_count,
    mark_notification_read,
    start_workflow_instance,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.workflow import (
    EscalationSweepResponse,
    NotificationListResponse,
    NotificationResponse,
    WorkflowDefinitionCreate,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionResponse,
    WorkflowInstanceListResponse,
    WorkflowInstanceResponse,
    WorkflowInstanceStart,
    WorkflowTaskCompleteRequest,
    WorkflowTaskResponse,
)
from app.utils.dependencies import get_current_active_user
from app.utils.dependencies import get_current_active_superuser

router = APIRouter(prefix="", tags=["Workflow"])


@router.get("/definitions", response_model=WorkflowDefinitionListResponse, summary="List workflow definitions")
async def list_workflow_definitions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    entity_type: str | None = Query(None),
    is_active: bool | None = Query(None),
) -> WorkflowDefinitionListResponse:
    definitions = await get_workflow_definitions(db, skip=skip, limit=limit, entity_type=entity_type, is_active=is_active)
    total = await get_workflow_definitions_count(db, entity_type=entity_type, is_active=is_active)
    return WorkflowDefinitionListResponse(
        items=[WorkflowDefinitionResponse.model_validate(d) for d in definitions], total=total, skip=skip, limit=limit
    )


@router.post(
    "/definitions",
    response_model=WorkflowDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workflow definition",
)
async def create_workflow_definition_endpoint(
    definition_data: WorkflowDefinitionCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> WorkflowDefinitionResponse:
    definition = await create_workflow_definition(db, definition_data, created_by=current_user.id)
    return WorkflowDefinitionResponse.model_validate(definition)


@router.get("/definitions/{definition_id}", response_model=WorkflowDefinitionResponse, summary="Get a workflow definition")
async def get_workflow_definition_endpoint(
    definition_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> WorkflowDefinitionResponse:
    definition = await get_workflow_definition(db, definition_id)
    if not definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow definition not found")
    return WorkflowDefinitionResponse.model_validate(definition)


@router.delete("/definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_definition_endpoint(
    definition_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_superuser)],
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        deleted = await delete_workflow_definition(db, definition_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow definition not found")


@router.get("/instances", response_model=WorkflowInstanceListResponse, summary="List workflow instances")
async def list_workflow_instances(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    entity_type: str | None = Query(None),
    entity_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
) -> WorkflowInstanceListResponse:
    instances = await get_workflow_instances(
        db, skip=skip, limit=limit, entity_type=entity_type, entity_id=entity_id, status=status_filter
    )
    total = await get_workflow_instances_count(db, entity_type=entity_type, entity_id=entity_id, status=status_filter)
    return WorkflowInstanceListResponse(
        items=[WorkflowInstanceResponse.model_validate(i) for i in instances], total=total, skip=skip, limit=limit
    )


@router.post(
    "/instances",
    response_model=WorkflowInstanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a workflow instance against a business entity",
)
async def start_workflow_instance_endpoint(
    start_data: WorkflowInstanceStart,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> WorkflowInstanceResponse:
    try:
        instance = await start_workflow_instance(db, start_data, started_by=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return WorkflowInstanceResponse.model_validate(instance)


@router.get("/instances/{instance_id}", response_model=WorkflowInstanceResponse, summary="Get a workflow instance and its tasks")
async def get_workflow_instance_endpoint(
    instance_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> WorkflowInstanceResponse:
    instance = await get_workflow_instance(db, instance_id)
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow instance not found")
    return WorkflowInstanceResponse.model_validate(instance)


@router.get("/tasks/my", response_model=list[WorkflowTaskResponse], summary="List my assigned workflow tasks")
async def list_my_tasks_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query("pending", alias="status"),
) -> list[WorkflowTaskResponse]:
    tasks = await get_my_tasks(db, current_user.id, status=status_filter)
    return [WorkflowTaskResponse.model_validate(t) for t in tasks]


@router.post("/tasks/{task_id}/complete", response_model=WorkflowTaskResponse, summary="Approve or reject a workflow task")
async def complete_task_endpoint(
    task_id: UUID,
    decision_data: WorkflowTaskCompleteRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> WorkflowTaskResponse:
    try:
        task = await complete_task(
            db, task_id, actor_id=current_user.id, decision=decision_data.decision, comments=decision_data.comments
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow task not found")
    return WorkflowTaskResponse.model_validate(task)


@router.post(
    "/escalate",
    response_model=EscalationSweepResponse,
    summary="Escalate all overdue pending approval tasks",
    description="Sweeps for pending tasks past their due date and escalates them. "
    "Intended to be called by a scheduled job; safe to call on-demand too.",
)
async def escalate_overdue_tasks_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> EscalationSweepResponse:
    escalated = await escalate_overdue_tasks(db)
    return EscalationSweepResponse(escalated_task_ids=[t.id for t in escalated], count=len(escalated))


@router.get("/notifications", response_model=NotificationListResponse, summary="List my notifications")
async def list_notifications_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    unread_only: bool = Query(False),
) -> NotificationListResponse:
    notifications = await get_notifications(db, current_user.id, skip=skip, limit=limit, unread_only=unread_only)
    total = await get_notifications_count(db, current_user.id, unread_only=unread_only)
    unread_count = await get_notifications_count(db, current_user.id, unread_only=True)
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        unread_count=unread_count,
        skip=skip,
        limit=limit,
    )


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse, summary="Mark a notification read")
async def mark_notification_read_endpoint(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    notification = await mark_notification_read(db, notification_id, recipient_id=current_user.id)
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return NotificationResponse.model_validate(notification)
