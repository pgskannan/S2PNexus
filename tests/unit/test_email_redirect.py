"""Unit tests for the Email Redirect decision engine (spec Section 3).

Covers the 5-step pipeline, the production interlock, and the config model.
"""

import pytest

from app.core.config import Settings
from app.middleware.email_redirect import (
    EmailRedirectMiddleware,
    EmailType,
    apply_redirect,
)

_REQUIRED = {
    "SECRET_KEY": "a" * 32,
    "DATABASE_URL": "postgresql://user:password@localhost:5432/s2pnexus",
}


def _settings(**overrides) -> Settings:
    return Settings(**{**_REQUIRED, **overrides})


def _middleware(**overrides) -> EmailRedirectMiddleware:
    return EmailRedirectMiddleware(_settings(**overrides))


# --------------------------------------------------------------------------
# Step 1 — flag on/off
# --------------------------------------------------------------------------
def test_redirect_disabled_sends_to_real_user() -> None:
    mw = _middleware(ENVIRONMENT="development", EMAIL_REDIRECT_ENABLED=False)
    d = mw.decide(EmailType.ORDER_CONFIRMATION.value, "buyer@acme.com")
    assert d.redirected is False
    assert d.effective_recipient == "buyer@acme.com"
    assert d.reason == "email_redirect_enabled=false"


def test_redirect_enabled_redirects_redirectable_type() -> None:
    mw = _middleware(
        ENVIRONMENT="development",
        EMAIL_REDIRECT_ENABLED=True,
        EMAIL_REDIRECT_TO="qa-inbox@acme.com",
    )
    d = mw.decide(EmailType.ORDER_CONFIRMATION.value, "buyer@acme.com")
    assert d.redirected is True
    assert d.effective_recipient == "qa-inbox@acme.com"
    assert d.original_recipient == "buyer@acme.com"


# --------------------------------------------------------------------------
# Step 2 — email type classification
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "email_type",
    [
        EmailType.USER_WELCOME.value,
        EmailType.USER_PASSWORD_INITIAL.value,
        EmailType.USER_PASSWORD_RESET.value,
    ],
)
def test_non_redirectable_types_always_go_to_real_user(email_type: str) -> None:
    mw = _middleware(
        ENVIRONMENT="development",
        EMAIL_REDIRECT_ENABLED=True,
        EMAIL_REDIRECT_TO="qa-inbox@acme.com",
    )
    d = mw.decide(email_type, "new-user@acme.com")
    assert d.redirected is False
    assert d.effective_recipient == "new-user@acme.com"
    assert "non-redirectable" in d.reason


def test_redirectable_types_are_all_redirected() -> None:
    mw = _middleware(
        ENVIRONMENT="staging",
        EMAIL_REDIRECT_ENABLED=True,
        EMAIL_REDIRECT_TO="qa-inbox@acme.com",
    )
    for email_type in (
        EmailType.ORDER_CONFIRMATION.value,
        EmailType.WORKFLOW_NOTIFICATION.value,
        EmailType.APPROVAL_NOTIFICATION.value,
        EmailType.GENERIC_NOTIFICATION.value,
    ):
        d = mw.decide(email_type, "approver@acme.com")
        assert d.redirected is True, f"{email_type} should be redirected"


# --------------------------------------------------------------------------
# Step 0 — production interlock
# --------------------------------------------------------------------------
def test_production_never_redirects_even_when_flag_set() -> None:
    # Config rejects production+flag at load; construct a settings object with
    # the flag flipped post-load to prove the middleware itself is the backstop.
    settings = _settings(ENVIRONMENT="production", EMAIL_REDIRECT_ENABLED=False)
    settings.EMAIL_REDIRECT_ENABLED = True
    settings.EMAIL_REDIRECT_TO = "qa-inbox@acme.com"
    mw = EmailRedirectMiddleware(settings)
    d = mw.decide(EmailType.ORDER_CONFIRMATION.value, "buyer@acme.com")
    assert d.redirected is False
    assert d.effective_recipient == "buyer@acme.com"
    assert "safety interlock" in d.reason


def test_config_rejects_redirect_in_production() -> None:
    with pytest.raises(ValueError, match="EMAIL_REDIRECT_ENABLED must be false"):
        _settings(
            ENVIRONMENT="production",
            EMAIL_REDIRECT_ENABLED=True,
            EMAIL_REDIRECT_TO="qa-inbox@acme.com",
        )


# --------------------------------------------------------------------------
# Step 3 — missing target fails closed
# --------------------------------------------------------------------------
def test_missing_redirect_target_fails_closed_to_real_user() -> None:
    mw = _middleware(ENVIRONMENT="development", EMAIL_REDIRECT_ENABLED=True, EMAIL_REDIRECT_TO=None)
    d = mw.decide(EmailType.ORDER_CONFIRMATION.value, "buyer@acme.com")
    assert d.redirected is False
    assert d.effective_recipient == "buyer@acme.com"
    assert "fail-closed" in d.reason


# --------------------------------------------------------------------------
# Config model
# --------------------------------------------------------------------------
def test_email_redirect_active_property() -> None:
    s = _settings(
        ENVIRONMENT="development",
        EMAIL_REDIRECT_ENABLED=True,
        EMAIL_REDIRECT_TO="qa-inbox@acme.com",
    )
    assert s.email_redirect_active is True


def test_email_redirect_active_false_in_production() -> None:
    s = _settings(ENVIRONMENT="production", EMAIL_REDIRECT_ENABLED=False)
    assert s.email_redirect_active is False


def test_email_provider_default_and_validation() -> None:
    s = _settings(EMAIL_PROVIDER="gmail")
    assert s.EMAIL_PROVIDER == "gmail"
    with pytest.raises(ValueError):
        _settings(EMAIL_PROVIDER="carrier-pigeon")


def test_invalid_redirect_to_rejected() -> None:
    with pytest.raises(ValueError):
        _settings(
            ENVIRONMENT="development",
            EMAIL_REDIRECT_ENABLED=True,
            EMAIL_REDIRECT_TO="not-an-email",
        )


def test_apply_redirect_returns_auditable_decision() -> None:
    settings = _settings(
        ENVIRONMENT="development",
        EMAIL_REDIRECT_ENABLED=True,
        EMAIL_REDIRECT_TO="qa-inbox@acme.com",
    )
    d = apply_redirect(EmailType.GENERIC_NOTIFICATION.value, "user@acme.com", settings=settings)
    assert d.redirected is True
    audit = d.to_audit_dict()
    assert audit["event"] == "email.redirected"
    assert audit["email_type"] == EmailType.GENERIC_NOTIFICATION.value
    assert audit["original_recipient"] == "user@acme.com"
    assert audit["effective_recipient"] == "qa-inbox@acme.com"
