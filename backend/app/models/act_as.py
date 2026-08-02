"""Act as User (admin impersonation) session tracking.

Scoped as a functional MVP (2026-08-01): any administrator can act as any
non-admin user, gets a short-lived impersonation token, and every session is
logged here for audit. Deliberately deferred from the full spec: no
per-tenant policy service, no approval-gated impersonation requests, no
automatic per-action business-object audit trail (VIEW/CREATE/UPDATE/APPROVE
on PRs/POs/etc while impersonating isn't separately tagged yet -- only
session start/end is). See app/routers/act_as.py for the session lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class ActAsSession(Base):
    __tablename__ = "act_as_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "manual" (admin clicked Exit) | "expired" (session hit expires_at,
    # recorded lazily -- see crud.act_as.end_act_as_session) | "superseded"
    # (admin started a new act-as session while an old one was still open)
    ended_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
