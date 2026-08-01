"""
Email redirect middleware (S2PNexus Email Redirect feature, spec Section 3).

This is a *service-level* middleware: email is not an HTTP request, so instead
of an ASGI middleware it is a decision service that the email service invokes
for every outbound message. It implements the canonical 5-step pipeline:

    1. Check EMAIL_REDIRECT_ENABLED
    2. Check email type
    3. If redirectable      -> replace recipient with EMAIL_REDIRECT_TO
    4. If non-redirectable  -> send to actual user
    5. Log the redirect event for audit

Safety invariants:
  * Production never redirects, even if the flag is set (enforced both here and
    at config load, where the app refuses to start).
  * Welcome / initial-password / password-reset mail is NEVER redirected.
  * If EMAIL_REDIRECT_TO is missing while the flag is on, we FAIL CLOSED and
    send to the real user rather than silently dropping mail.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.core.config import get_settings

# Canonical email types. Every outbound message must declare one of these.
class EmailType(str, Enum):
    ORDER_CONFIRMATION = "order.confirmation"
    WORKFLOW_NOTIFICATION = "workflow.notification"
    APPROVAL_NOTIFICATION = "approval.notification"
    GENERIC_NOTIFICATION = "system.notification"
    USER_WELCOME = "user.welcome"
    USER_PASSWORD_INITIAL = "user.password_initial"
    USER_PASSWORD_RESET = "user.password_reset"


# Emails that MUST always reach the actual user (never redirected).
# Spec Section 1: Welcome Email, Password Email (initial), Password Reset Email.
NON_REDIRECTABLE_EMAIL_TYPES: frozenset[str] = frozenset(
    {
        EmailType.USER_WELCOME.value,
        EmailType.USER_PASSWORD_INITIAL.value,
        EmailType.USER_PASSWORD_RESET.value,
    }
)


@dataclass
class RedirectDecision:
    """Immutable result of evaluating the redirect pipeline for one email."""

    email_type: str
    original_recipient: str
    effective_recipient: str
    redirected: bool
    redirect_target: Optional[str] = None
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_audit_dict(self) -> dict:
        """Structured audit payload (spec Section 3 — Audit logging)."""
        return {
            "event": "email.redirected" if self.redirected else "email.sent_direct",
            "email_type": self.email_type,
            "original_recipient": self.original_recipient,
            "effective_recipient": self.effective_recipient,
            "redirect_target": self.redirect_target,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "environment": None,  # filled by caller when known
        }


class EmailRedirectMiddleware:
    """Decides the effective recipient for an outbound email.

    The middleware is stateless; instantiate one module-level singleton and
    reuse it. It is intentionally NOT an ASGI middleware because email is sent
    from service code, not handled over HTTP.
    """

    def __init__(self, settings=None) -> None:
        self._settings = settings if settings is not None else get_settings()

    # -- step 1: flag check -------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(self._settings.EMAIL_REDIRECT_ENABLED)

    @property
    def redirect_to(self) -> Optional[str]:
        return self._settings.EMAIL_REDIRECT_TO

    # -- step 2: type check -------------------------------------------------
    def is_non_redirectable(self, email_type: str) -> bool:
        return email_type in NON_REDIRECTABLE_EMAIL_TYPES

    # -- the 5-step pipeline ------------------------------------------------
    def decide(self, email_type: str, recipient: str) -> RedirectDecision:
        """Evaluate the pipeline and return the recipient decision.

        Args:
            email_type: one of EmailType values (or a custom domain type).
            recipient:  the original intended recipient email address.

        Returns:
            A RedirectDecision carrying the effective recipient and audit info.
        """
        settings = self._settings

        # Step 0 — production interlock. Even if the config validator is bypassed
        # (e.g. settings constructed programmatically), never redirect in prod.
        if settings.is_production:
            return RedirectDecision(
                email_type=email_type,
                original_recipient=recipient,
                effective_recipient=recipient,
                redirected=False,
                reason="environment=production; redirect disabled by safety interlock",
            )

        # Step 1 — flag off => everything goes to the real user.
        if not self.enabled:
            return RedirectDecision(
                email_type=email_type,
                original_recipient=recipient,
                effective_recipient=recipient,
                redirected=False,
                reason="email_redirect_enabled=false",
            )

        # Step 2 — non-redirectable types always go to the real user.
        if self.is_non_redirectable(email_type):
            return RedirectDecision(
                email_type=email_type,
                original_recipient=recipient,
                effective_recipient=recipient,
                redirected=False,
                reason=f"email_type={email_type} is non-redirectable",
            )

        # Step 3 — target must be configured; fail closed to the real user if not.
        target = self.redirect_to
        if not target:
            return RedirectDecision(
                email_type=email_type,
                original_recipient=recipient,
                effective_recipient=recipient,
                redirected=False,
                reason="email_redirect_to missing; fail-closed to real recipient",
            )

        # Step 4 — redirectable: swap the recipient.
        return RedirectDecision(
            email_type=email_type,
            original_recipient=recipient,
            effective_recipient=target,
            redirected=True,
            redirect_target=target,
            reason=f"redirected {email_type} in environment={settings.ENVIRONMENT}",
        )


# Module-level singleton so callers share one instance.
email_redirect_middleware = EmailRedirectMiddleware()


def apply_redirect(
    email_type: str,
    recipient: str,
    *,
    settings=None,
    middleware: Optional[EmailRedirectMiddleware] = None,
) -> RedirectDecision:
    """Convenience wrapper: decide + emit structured audit log.

    Returns the decision so the caller can use effective_recipient. The audit
    line is always emitted (both for redirected and non-redirected sends) so the
    log is a complete, queryable trail.
    """
    from app.core.logging import get_logger

    settings = settings if settings is not None else get_settings()
    mw = middleware if middleware is not None else EmailRedirectMiddleware(settings)
    decision = mw.decide(email_type, recipient)
    audit = decision.to_audit_dict()
    audit["environment"] = settings.ENVIRONMENT
    event = audit.pop("event", "email_redirect_decision")
    get_logger("s2pnexus.email.redirect").info(event, **audit)
    return decision
