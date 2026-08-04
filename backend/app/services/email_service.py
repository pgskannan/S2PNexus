"""
Enterprise email service for S2PNexus (Email Redirect spec, Section 3).

Single entry point for ALL outbound email. Responsibilities:

  * Render an HTML template (+ plain-text fallback) from the template store.
  * Apply the EmailRedirectMiddleware pipeline before delivery so DEV/QA/Sandbox
    redirectable mail lands in EMAIL_REDIRECT_TO while user-critical mail
    (welcome, initial password, password reset) always reaches the real user.
  * Deliver through a pluggable EmailProvider (Gmail SMTP, generic SMTP, or a
    future API-based provider).
  * Emit a structured audit record for every send attempt.

Template engine is dependency-free and intentionally minimal. Supported syntax:

    {{variable}}                    HTML-escaped value
    {{#each orderItems}}...{{/each}}  repeat block once per list item
    {{#if condition}}...{{/if}}       include block only when truthy

Inside an {{#each}} block, item fields are merged into scope, e.g.
{{productName}}, {{quantity}}, {{unitPrice}}.
"""

from __future__ import annotations

import re
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from uuid import uuid4

from app.core.config import get_settings
from app.middleware.email_redirect import EmailType, RedirectDecision, apply_redirect

# Templates live next to the app package: backend/app/templates/email/
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

# --------------------------------------------------------------------------
# Template engine (Section 4 — enterprise templates)
# --------------------------------------------------------------------------
_VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")
_EACH_RE = re.compile(r"\{\{#each\s+([A-Za-z0-9_.]+)\}\}(.*?)\{\{/each\}\}", re.DOTALL)
_IF_RE = re.compile(r"\{\{#if\s+([A-Za-z0-9_.]+)\}\}(.*?)\{\{/if\}\}", re.DOTALL)


def _lookup(context: Mapping[str, Any], path: str) -> Any:
    cur: Any = context
    for part in path.split("."):
        if isinstance(cur, Mapping):
            cur = cur.get(part)
        else:
            return None
    return cur


def _render_each(template: str, context: Mapping[str, Any]) -> str:
    def repl(match: re.Match) -> str:
        key, body = match.group(1), match.group(2)
        items = _lookup(context, key)
        if not isinstance(items, (list, tuple)):
            return ""
        parts = []
        for item in items:
            if isinstance(item, Mapping):
                parts.append(render_template(body, {**context, **item}))
            else:
                parts.append(render_template(body, {**context, "this": item}))
        return "".join(parts)

    while _EACH_RE.search(template):
        template = _EACH_RE.sub(repl, template)
    return template


def _render_if(template: str, context: Mapping[str, Any]) -> str:
    def repl(match: re.Match) -> str:
        key, body = match.group(1), match.group(2)
        value = _lookup(context, key)
        truthy = bool(value) and value not in (0, 0.0, "0", "false", "False", "off")
        return render_template(body, context) if truthy else ""

    while _IF_RE.search(template):
        template = _IF_RE.sub(repl, template)
    return template


def _render_vars(template: str, context: Mapping[str, Any]) -> str:
    def repl(match: re.Match) -> str:
        value = _lookup(context, match.group(1))
        if value is None:
            return ""
        if isinstance(value, (Mapping, list, tuple)):
            value = str(value)
        return escape(str(value), quote=True)

    return _VAR_RE.sub(repl, template)


def render_template(template: str, context: Mapping[str, Any]) -> str:
    """Render a template with {{var}}, {{#each}}, and {{#if}} support."""
    return _render_vars(_render_if(_render_each(template, context), context), context)


def load_template(name: str) -> str:
    """Load an HTML template by filename from the email template directory."""
    path = TEMPLATE_DIR / f"{name}.html"
    return path.read_text(encoding="utf-8")


def strip_html(html_body: str) -> str:
    """Best-effort plain-text fallback derived from an HTML body."""
    text = re.sub(r"<br\s*/?>", "\n", html_body, flags=re.IGNORECASE)
    text = re.sub(r"</(p|tr|div|h[1-6]|li)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(td|th)>", " | ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = escape(text, quote=False)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------
def _normalize_app_password(raw: Optional[str]) -> Optional[str]:
    """Normalize an SMTP/App password for login.

    Gmail App Passwords are often pasted in the 'xxxx xxxx xxxx xxxx' format;
    strip all whitespace so the 16-character code logs in reliably.
    Returns None when the input is empty/None.
    """
    if not raw:
        return None
    return "".join(raw.split())


class EmailProvider(ABC):
    """Transport abstraction. Implementers deliver an EmailMessage."""

    def __init__(self, settings) -> None:
        self._settings = settings

    @property
    def display_name(self) -> str:
        return type(self).__name__

    @abstractmethod
    def send(self, message: EmailMessage) -> None:
        """Deliver the message. Raises EmailDeliveryError on failure."""


class GmailSmtpProvider(EmailProvider):
    """Gmail SMTP via smtp.gmail.com:587 with STARTTLS (requires an App Password)."""

    HOST = "smtp.gmail.com"
    PORT = 587

    def send(self, message: EmailMessage) -> None:
        username = self._settings.EMAIL_USERNAME or self._settings.SMTP_USERNAME
        password = _normalize_app_password(self._settings.EMAIL_PASSWORD or self._settings.SMTP_PASSWORD)
        if not username or not password:
            raise EmailDeliveryError(
                "Gmail SMTP requires EMAIL_USERNAME and EMAIL_PASSWORD (App Password)."
            )
        context = ssl.create_default_context()
        with smtplib.SMTP(self.HOST, self.PORT, timeout=30) as server:
            server.ehlo()
            if self._settings.SMTP_TLS:
                server.starttls(context=context)
                server.ehlo()
            server.login(username, password)
            server.send_message(message)


class GenericSmtpProvider(EmailProvider):
    """Provider-agnostic SMTP using SMTP_HOST/SMTP_PORT/SMTP_TLS from settings."""

    def send(self, message: EmailMessage) -> None:
        host = self._settings.smtp_host_resolved
        port = self._settings.smtp_port_resolved
        username = self._settings.EMAIL_USERNAME or self._settings.SMTP_USERNAME
        password = _normalize_app_password(self._settings.EMAIL_PASSWORD or self._settings.SMTP_PASSWORD)
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            if self._settings.SMTP_TLS:
                server.starttls(context=context)
                server.ehlo()
            if username and password:
                server.login(username, password)
            server.send_message(message)


def build_provider(settings=None) -> EmailProvider:
    """Instantiate the provider selected by EMAIL_PROVIDER."""
    settings = settings if settings is not None else get_settings()
    provider_name = settings.EMAIL_PROVIDER
    if provider_name == "gmail":
        return GmailSmtpProvider(settings)
    if provider_name in ("sendgrid", "ses"):
        raise EmailDeliveryError(
            f"EMAIL_PROVIDER={provider_name} is reserved; only 'gmail' and 'smtp' "
            "are wired up in this build."
        )
    return GenericSmtpProvider(settings)


class EmailDeliveryError(Exception):
    """Raised when an email cannot be delivered."""


@dataclass
class SendResult:
    """Outcome of one send attempt."""

    message_id: str
    email_type: str
    original_recipient: str
    effective_recipient: str
    redirected: bool
    decision: RedirectDecision


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------
class EmailService:
    """High-level API used by the rest of the application."""

    def __init__(self, settings=None, provider: Optional[EmailProvider] = None) -> None:
        self._settings = settings if settings is not None else get_settings()
        self._provider = provider or build_provider(self._settings)

    # -- public API --------------------------------------------------------
    async def send_email(
        self,
        *,
        email_type: str,
        to: str,
        subject: str,
        template: str,
        context: Mapping[str, Any],
        from_addr: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Sequence[str] = (),
        bcc: Sequence[str] = (),
        tenant_id: Optional[Any] = None,
    ) -> SendResult:
        """Render, redirect, and send one email.

        The redirect decision is applied here, inside the service, so no caller
        can accidentally bypass it. Returns a SendResult with audit info.

        Admin template overrides (backlog Section 1): an active
        ``EmailTemplateOverride`` for ``email_type`` (+ tenant) overrides the
        subject/body/footer/logo *content* before sending. Overrides never
        touch the redirect pipeline — delivery behavior is unchanged.
        """
        # Step 1-4 of the pipeline: decide the effective recipient.
        # Use this service's settings so tests/embedded configs control behavior.
        decision: RedirectDecision = apply_redirect(email_type, to, settings=self._settings)

        # Admin-configurable content overrides. Only fields the admin actually
        # set are applied; everything else falls back to the catalog/default.
        merged_context = dict(context)
        override = await self._resolve_override(email_type, tenant_id=tenant_id)
        if override is not None:
            # The template engine resolves {{tenant.footer}}/{{tenant.logo}}
            # via nested dict lookup, so inject them into the nested "tenant"
            # scope (preserving any caller-supplied tenant fields).
            tenant = dict(merged_context.get("tenant") or {})
            if override.footer_override:
                tenant["footer"] = override.footer_override
            if override.branding_logo_url:
                tenant["logo"] = override.branding_logo_url
            if tenant:
                merged_context["tenant"] = tenant
            if override.subject_override:
                subject = render_template(override.subject_override, merged_context)

        if override is not None and override.html_override:
            body_source = override.html_override
        else:
            body_source = load_template(template)

        html_body = render_template(body_source, merged_context)
        text_body = strip_html(html_body)

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr(
            (from_name or self._settings.EMAIL_FROM_NAME, from_addr or self._settings.EMAIL_FROM)
        )
        msg["To"] = decision.effective_recipient
        if reply_to:
            msg["Reply-To"] = reply_to
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        msg["Message-ID"] = f"<{uuid4().hex}@s2pnexus>"
        msg["X-S2PNexus-Email-Type"] = email_type
        msg["X-S2PNexus-Redirected"] = "true" if decision.redirected else "false"
        msg["X-S2PNexus-Original-To"] = decision.original_recipient
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        try:
            self._provider.send(msg)
        except Exception as exc:  # noqa: BLE001 - deliver a clean audit line
            self._log_audit(decision, subject=subject, status="failed", error=str(exc))
            raise EmailDeliveryError(f"Email delivery failed: {exc}") from exc

        self._log_audit(decision, subject=subject, status="sent")
        return SendResult(
            message_id=msg["Message-ID"],
            email_type=email_type,
            original_recipient=decision.original_recipient,
            effective_recipient=decision.effective_recipient,
            redirected=decision.redirected,
            decision=decision,
        )

    # -- convenience senders (used by routers/services) --------------------
    async def _resolve_override(self, email_type: str, tenant_id: Any = None):
        """Resolve the active admin override for ``email_type`` (+ tenant).

        Returns the most specific active ``EmailTemplateOverride``:
        tenant-specific first, then the global (``tenant_id`` IS NULL) row.
        Any DB failure returns None so an admin override can never break
        delivery — the catalog/default template is used instead.
        """
        try:
            from sqlalchemy import select

            from app.database.database import db_manager
            from app.models.email_template import EmailTemplateOverride

            async with db_manager.session() as session:
                rows = (
                    await session.execute(
                        select(EmailTemplateOverride).where(
                            EmailTemplateOverride.email_type == email_type,
                            EmailTemplateOverride.is_active.is_(True),
                        )
                    )
                ).scalars().all()
        except Exception:  # noqa: BLE001 - override must never break delivery
            return None

        if tenant_id is not None:
            for row in rows:
                if row.tenant_id is not None and row.tenant_id == tenant_id:
                    return row
        for row in rows:
            if row.tenant_id is None:
                return row
        return None

    async def send_welcome_email(self, *, to: str, userName: str, activationLink: str) -> SendResult:
        """New user onboarding — NEVER redirected (spec Section 1)."""
        return await self.send_email(
            email_type=EmailType.USER_WELCOME.value,
            to=to,
            subject="Welcome to S2PNexus — Your Account Is Ready",
            template="welcome_email",
            context={
                "userName": userName,
                "email": to,
                "activationLink": activationLink,
                "supportEmail": self._settings.EMAIL_FROM,
                "loginUrl": "https://s2pnexus.example.com/login",
                "year": "2026",
            },
        )

    async def send_password_reset_email(self, *, to: str, userName: str, resetLink: str) -> SendResult:
        """Password reset — NEVER redirected (spec Section 1)."""
        return await self.send_email(
            email_type=EmailType.USER_PASSWORD_RESET.value,
            to=to,
            subject="S2PNexus Password Reset Request",
            template="password_reset_email",
            context={
                "userName": userName,
                "resetLink": resetLink,
                "expiresIn": "60 minutes",
                "supportEmail": self._settings.EMAIL_FROM,
                "year": "2026",
            },
        )

    async def send_order_confirmation_email(
        self, *, to: str, userName: str, orderNumber: str, orderItems: list[dict[str, Any]], totalAmount: str
    ) -> SendResult:
        """Order confirmation — redirectable in DEV/QA/Sandbox (spec Section 1)."""
        return await self.send_email(
            email_type=EmailType.ORDER_CONFIRMATION.value,
            to=to,
            subject=f"S2PNexus Order Confirmation — {orderNumber}",
            template="order_confirmation_email",
            context={
                "userName": userName,
                "orderNumber": orderNumber,
                "orderDate": "2026-08-01",
                "orderItems": orderItems,
                "totalAmount": totalAmount,
                "supportEmail": self._settings.EMAIL_FROM,
                "year": "2026",
            },
        )

    async def send_purchase_order_email(
        self,
        *,
        to: str,
        poNumber: str,
        buyerName: str = "",
        companyName: str = "",
        currency: str = "",
        poTotal: str = "",
        shipToAddress: str = "",
        paymentTerms: str = "",
        deliveryDate: str = "",
        poDate: str = "",
        ackDeadline: str = "",
        acknowledgeUrl: str = "",
        tenant_id: Optional[Any] = None,
    ) -> SendResult:
        """PO dispatched to the supplier for acknowledgement -- redirectable in
        DEV/QA/Sandbox like order confirmations (spec: "PO auto-sent to
        supplier"). Template ported from templates_catalog.json's
        `po_dispatch_v1` entry, which was cataloged but never wired to an
        actual .html file / send path."""
        return await self.send_email(
            email_type=EmailType.PO_DISPATCH.value,
            to=to,
            subject=f"{companyName or 'S2PNexus'} — Purchase Order {poNumber} Dispatch",
            template="po_dispatch_email",
            context={
                "poNumber": poNumber,
                "buyerName": buyerName,
                "companyName": companyName,
                "currency": currency,
                "poTotal": poTotal,
                "shipToAddress": shipToAddress,
                "paymentTerms": paymentTerms,
                "deliveryDate": deliveryDate,
                "poDate": poDate,
                "ackDeadline": ackDeadline,
                "acknowledgeUrl": acknowledgeUrl,
                "year": "2026",
            },
            tenant_id=tenant_id,
        )

    # -- audit -------------------------------------------------------------
    def _log_audit(
        self, decision: RedirectDecision, *, subject: str, status: str, error: str | None = None
    ) -> None:
        """Emit a structured audit record (spec Section 3 — Audit logging).

        Every send produces one line, redirected or not, so the trail is
        complete and searchable. Persist to an audit table (see spec) if DB
        retention is required; the JSON line is the source of truth here.
        """
        from app.core.logging import get_logger

        get_logger("s2pnexus.email.audit").info(
            "email_send",
            message_id=uuid4().hex,
            email_type=decision.email_type,
            subject=subject,
            original_recipient=decision.original_recipient,
            effective_recipient=decision.effective_recipient,
            redirected=decision.redirected,
            redirect_target=decision.redirect_target,
            status=status,
            error=error,
            environment=self._settings.ENVIRONMENT,
        )


# Module-level singleton.
email_service = EmailService()
