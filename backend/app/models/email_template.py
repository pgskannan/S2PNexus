"""EmailTemplateOverride model for admin-configurable lifecycle email templates.

Implements the "Admin can configure PO email template: subject, body, footer,
branding, instructions" requirement (P2P UX backlog Section 1). A row exists
only when an admin has overridden something for an ``email_type`` (a catalog
``email_type`` such as ``po.dispatch`` from
``backend/app/templates/email/templates_catalog.json``). Any null override
field falls back to the catalog default at send time — admins never have to
redefine a whole template to change one line.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class EmailTemplateOverride(Base):
    """Admin-configured override for one ``email_type`` (per tenant or global).

    - ``tenant_id`` NULL means the global default; a non-NULL value is a
      tenant-specific override that wins over the global row.
    - Only fields that differ from the catalog default are stored; a null
      override field falls back to the catalog default at send time.
    - ``is_active=False`` disables the override so the catalog default is used.
    """

    __tablename__ = "email_template_overrides"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email_type", name="uq_email_template_overrides_tenant_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique identifier",
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Tenant this override applies to; NULL = global default",
    )
    email_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Catalog email_type, e.g. 'po.dispatch'",
    )
    subject_override: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Overrides the email subject; may contain {{variables}}",
    )
    html_override: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Full HTML body override; replaces the catalog/default template",
    )
    footer_override: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Footer text injected via the {{tenant.footer}} template variable",
    )
    branding_logo_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        comment="Logo URL injected via the {{tenant.logo}} template variable",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="False disables the override (falls back to catalog default)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last update timestamp",
    )
