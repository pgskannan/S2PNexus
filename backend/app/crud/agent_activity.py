"""CRUD helpers for the Agent Activity Log.

See `app.models.agent_activity.AgentActivityLog` for the model and
`app.routers.ai.query_agents` for the write path (best-effort, non-fatal).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_activity import AgentActivityLog


def _extract_tools_used(data: dict[str, Any]) -> list[str]:
    """Best-effort extraction of which tools contributed grounding data.

    `LLMBackedAgent.execute()` shapes `data` as
    `{"request": ..., "tool_data": {tool_name: result, ...}, "llm_used": bool}`.
    Placeholder agents (not yet upgraded) may not include `tool_data` at all --
    in that case we just report no tools were used rather than erroring.
    """
    tool_data = data.get("tool_data")
    if isinstance(tool_data, dict):
        return list(tool_data.keys())
    return []


async def create_agent_activity_log(
    db: AsyncSession,
    *,
    agent_name: str,
    request_text: str,
    success: bool,
    message: str,
    plan: list[Any] | None,
    explanation: str | None,
    data: dict[str, Any] | None,
    actor_id: uuid.UUID | str | None = None,
    latency_ms: int | None = None,
) -> AgentActivityLog:
    """Persist one agent invocation record. Callers should treat failures as non-fatal."""
    data = data or {}
    log = AgentActivityLog(
        agent_name=agent_name,
        request_text=request_text,
        success=success,
        message=message,
        plan=plan or [],
        explanation=explanation,
        tools_used=_extract_tools_used(data),
        llm_used=bool(data.get("llm_used", False)),
        data=data,
        actor_id=actor_id or None,
        latency_ms=latency_ms,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def get_agent_activity_log(db: AsyncSession, log_id: uuid.UUID) -> AgentActivityLog | None:
    result = await db.execute(select(AgentActivityLog).where(AgentActivityLog.id == log_id))
    return result.scalar_one_or_none()


async def list_agent_activity_logs(
    db: AsyncSession,
    *,
    agent_name: str | None = None,
    success: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentActivityLog], int]:
    """Return (rows, total_count) newest-first, optionally filtered by agent_name/success."""
    filters = []
    if agent_name:
        filters.append(AgentActivityLog.agent_name == agent_name)
    if success is not None:
        filters.append(AgentActivityLog.success == success)

    count_stmt = select(func.count()).select_from(AgentActivityLog)
    for f in filters:
        count_stmt = count_stmt.where(f)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = select(AgentActivityLog).order_by(AgentActivityLog.created_at.desc()).limit(limit).offset(offset)
    for f in filters:
        stmt = stmt.where(f)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), total


async def get_agent_activity_summary(db: AsyncSession) -> dict[str, Any]:
    """Aggregate counters for the dashboard header."""
    total = (await db.execute(select(func.count()).select_from(AgentActivityLog))).scalar_one()
    success_count = (
        await db.execute(select(func.count()).select_from(AgentActivityLog).where(AgentActivityLog.success.is_(True)))
    ).scalar_one()
    llm_used_count = (
        await db.execute(select(func.count()).select_from(AgentActivityLog).where(AgentActivityLog.llm_used.is_(True)))
    ).scalar_one()

    by_agent_rows = await db.execute(
        select(AgentActivityLog.agent_name, func.count()).group_by(AgentActivityLog.agent_name)
    )
    by_agent = {name: count for name, count in by_agent_rows.all()}

    return {
        "total_calls": total,
        "success_count": success_count,
        "failure_count": total - success_count,
        "llm_used_count": llm_used_count,
        "by_agent": by_agent,
    }
