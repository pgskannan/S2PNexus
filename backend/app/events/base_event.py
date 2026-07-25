from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass(slots=True)
class DomainEvent:
    """Standardized event envelope for all domain events across the platform.

    Every event published anywhere in S2PNexus uses this envelope so that
    subscribers, audit logs, and future event stores have a uniform contract.
    """

    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    aggregate_type: str = ""
    aggregate_id: str | None = None
    tenant_id: str | None = None
    actor: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = field(default_factory=dict)
