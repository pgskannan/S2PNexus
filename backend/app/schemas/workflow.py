"""Schemas for Workflow Automation: definitions, instances, tasks, notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

STEP_TYPES = ("condition", "approval", "notification", "auto", "ai")

# Step types allowed to carry `parallel_group` -- deliberately excludes
# "condition" (branching + fork/join in the same step would need a real
# nested-branch model) and "ai" (its auto-approve-or-fall-through-to-role
# behavior would need its own approver resolution inside the group; kept out
# of v1 to bound scope -- see crud/workflow.py's parallel-group handling).
PARALLEL_GROUP_MEMBER_TYPES = {"approval", "notification", "auto"}


class WorkflowStep(BaseModel):
    """One step of a workflow definition. Field relevance depends on step_type:

    - condition: field, operator, value, on_true_next_step, on_false_next_step
    - approval: approvers (or role_code for rule-driven resolution),
      required_approvals, escalate_after_hours, escalate_to, next_step
    - auto: deterministic auto-approval, next_step
    - ai: rules (deterministic + AI) may auto-approve or fall through to a role
    - notification: recipients, message_template, next_step

    True parallel branches (as opposed to the multiple-approvers-on-one-step
    "N-of-M" pattern) are expressed by giving two or more steps the same
    `parallel_group` value -- see crud/workflow.py::_run_from_step. All steps
    sharing a group are activated together (tasks created / notifications
    sent / auto-approvals recorded in the same pass) and the workflow only
    advances past the group once every approval-type member has reached its
    own `required_approvals`; a rejection on any member rejects the whole
    instance, matching single-step rejection semantics. `parallel_next_step`
    is where execution continues once the group is fully resolved (falls
    through to the step after the highest-indexed member if unset, same
    fallthrough convention as on_true_next_step/on_false_next_step).

    `next_step` on non-condition steps overrides the default "+1" continue
    target (use `len(steps)` for End). When unset, the runtime still skips
    falling from one Yes/No condition arm into its sibling -- see
    crud/workflow.py::_continue_after_step.
    """

    name: str = Field(..., min_length=1, max_length=255)
    step_type: Literal["condition", "approval", "notification", "auto", "ai"]

    # condition
    field: Optional[str] = None
    operator: Optional[Literal["eq", "neq", "gt", "gte", "lt", "lte", "in"]] = None
    value: Optional[Any] = None
    on_true_next_step: Optional[int] = None
    on_false_next_step: Optional[int] = None

    # approval / ai
    approvers: list[UUID] = Field(default_factory=list)
    role_code: Optional[str] = None
    required_approvals: int = Field(default=1, ge=1)
    escalate_after_hours: Optional[int] = Field(default=None, ge=1)
    escalate_to: Optional[UUID] = None
    # Human-readable "why this approval" -- shown as a hover tooltip on the
    # designer canvas node and editable / AI-drafted in the node inspector.
    reason: Optional[str] = Field(default=None, max_length=2000)
    rules: dict[str, Any] = Field(default_factory=dict)

    # Where to go after this step finishes (approval / notification / auto /
    # ai). `len(steps)` means End / workflow complete. When unset, runtime
    # uses +1 unless that would enter the sibling arm of a condition.
    next_step: Optional[int] = None

    # notification
    recipients: list[UUID] = Field(default_factory=list)
    message_template: Optional[str] = None

    # parallel branches (approval / notification / auto only -- see
    # PARALLEL_GROUP_MEMBER_TYPES)
    parallel_group: Optional[str] = Field(default=None, max_length=100)
    parallel_next_step: Optional[int] = None


class WorkflowDefinitionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    steps: list[WorkflowStep] = Field(..., min_length=1)
    is_active: bool = Field(default=True)
    # Definition lifecycle: draft / published / archived (defaults to published
    # for backward compatibility).
    status: Optional[str] = Field(default=None, pattern="^(draft|published|archived)$")

    @model_validator(mode="after")
    def _validate_parallel_groups(self) -> "WorkflowDefinitionCreate":
        groups: dict[str, list[int]] = {}
        for index, step in enumerate(self.steps):
            if not step.parallel_group:
                continue
            if step.step_type not in PARALLEL_GROUP_MEMBER_TYPES:
                raise ValueError(
                    f"Step {index} ('{step.name}'): parallel_group is only supported on "
                    f"{sorted(PARALLEL_GROUP_MEMBER_TYPES)} steps, not '{step.step_type}'"
                )
            groups.setdefault(step.parallel_group, []).append(index)

        for group_key, member_indices in groups.items():
            if len(member_indices) < 2:
                raise ValueError(
                    f"parallel_group '{group_key}' has only one member (step {member_indices[0]}) -- "
                    "a parallel group needs at least two steps to branch"
                )
            next_steps = {self.steps[i].parallel_next_step for i in member_indices}
            if len(next_steps) > 1:
                raise ValueError(
                    f"All steps in parallel_group '{group_key}' must set the same parallel_next_step "
                    f"(got {sorted(v for v in next_steps if v is not None)})"
                )
            next_step = next(iter(next_steps))
            if next_step is not None and not (0 <= next_step <= len(self.steps)):
                raise ValueError(
                    f"parallel_group '{group_key}': parallel_next_step {next_step} is out of range "
                    f"(must be between 0 and {len(self.steps)})"
                )
        return self

    @model_validator(mode="after")
    def _validate_approval_steps(self) -> "WorkflowDefinitionCreate":
        """An approval step that can never resolve an approver is a silent
        auto-approval waiting to happen. The runtime engine now blocks (rather
        than skips) such steps, but rejecting the definition up front is
        better. Mirrors the designer's client-side check."""
        for index, step in enumerate(self.steps):
            if step.step_type == "approval" and not step.approvers and not step.role_code:
                raise ValueError(
                    f"Step {index} ('{step.name}'): approval steps need at least one "
                    "approver, or a role_code to resolve approvers from"
                )
        return self


class WorkflowDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    entity_type: str
    description: Optional[str] = None
    steps: list[dict]
    is_active: bool
    status: str = "published"
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
    reason: Optional[str] = None
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


class WorkflowFieldSpec(BaseModel):
    path: str
    label: str
    type: str


class WorkflowFieldListResponse(BaseModel):
    entity_type: str
    fields: list[WorkflowFieldSpec]


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
