from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentContext:
    """Execution context passed to agents during orchestration."""

    request: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    rag_enabled: bool = False
    llm_enabled: bool = False
    selected_agent: str | None = None
    # Optional, added for real (LLM- and DB-grounded) agents. Both default to
    # None so existing callers/tests that construct an AgentContext without
    # them (e.g. unit tests exercising placeholder agents directly) keep working.
    db: Any = None
    tool_registry: Any = None
