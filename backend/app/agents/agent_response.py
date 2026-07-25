from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentResponse:
    """Structured response returned by an agent."""

    agent_name: str
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    plan: list[str] = field(default_factory=list)
    explanation: str = ""
