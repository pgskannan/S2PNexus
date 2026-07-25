"""Schemas for Workflow Automation: definitions, instances, tasks, notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

STEP_TYPES = ("condition", "approval", "notification")


class WorkflowStep(BaseModel):
    """One step of a workflow definition. Field relevance depends on step_type:

    - condition: field, operator, value, on_true_next_step, on_false_next_step
    - approval: approvers, required_approvals, escalate_after_hours, escalate_to
    - notification: recipients, message_template
    """

    name: str = Field(..., min_length=1, max_length=255)
    step_type: Literal["condition", "approval", "notification"]

    # condition
    field: Optional[str] = None
    operator: Optional[Literal["eq", "neq", "gt", "gte", "lt", "lte", "in"]] = None
    value: Optional[Any] = None
    on_true_next_step: Optional[int] = None
    on_false_next_step: Optional[int] = None

    # approval
    approvers: list[UUID] = Field(default_factory=list)
    required_approvals: int = Field(default=1, ge=1)
    escalate_after_hours: Optional[int] = Field(default=None, ge=1)
    escalate_to: Optional[UUID] = None

    # notification
    recipients: list[UUID] = Field(default_factory=list)
    message_template: Optional[str] = None


class WorkflowDefinitionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    steps: list[WorkflowStep] = Field(..., min_length=1)
    is_active: bool = Field(default=True)


class WorkflowDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    entity_type: str
    description: Optional[str] = None
    steps: list[dict]
    is_active: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class WorkflowDefinitionListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[WorkflowDefinitionResponse]
    total: int
    skip: int
    limit: int


class WorkflowInstanceStart(BaseModel):
    definition_id: UUID
    entity_type: str = Field(..., min_length=1, max_length=50)
    entity_id: UUID
    context: dict[str, Any] = Field(default_factory=dict, description="Snapshot of entity fields used to evaluate conditions")


class WorkflowTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    instance_id: UUID
    step_index: int
    step_name: str
    assignee_id: UUID
    status: str
    due_at: Optional[datetime] = None
    escalate_to: Optional[UUID] = None
    escalated_at: Optional[datetime] = None
    comments: Optional[str] = None
    completed_by: Optional[UUID] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class WorkflowInstanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    definition_id: UUID
    entity_type: str
    entity_id: UUID
    status: str
    current_step_index: int
    context: dict[str, Any]
    started_by: UUID
    started_at: datetime
    completed_at: Optional[datetime] = None
    tasks: list[WorkflowTaskResponse] = Field(default_factory=list)


class WorkflowInstanceListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[WorkflowInstanceResponse]
    total: int
    skip: int
    limit: int


class WorkflowTaskCompleteRequest(BaseModel):
    decision: Literal["approve", "reject"]
    comments: Optional[str] = None


class EscalationSweepResponse(BaseModel):
    escalated_task_ids: list[UUID]
    count: int


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    recipient_id: UUID
    title: str
    message: str
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[UUID] = None
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[NotificationResponse]
    total: int
    unread_count: int
    skip: int
    limit: int
