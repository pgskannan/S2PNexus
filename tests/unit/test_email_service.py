"""Unit tests for the email service + template engine (spec Sections 3 & 4)."""

import pytest

from app.core.config import Settings
from app.middleware.email_redirect import EmailType
from app.services.email_service import (
    EmailService,
    render_template,
    strip_html,
)

_REQUIRED = {
    "SECRET_KEY": "a" * 32,
    "DATABASE_URL": "postgresql://user:password@localhost:5432/s2pnexus",
}


def _settings(**overrides) -> Settings:
    return Settings(**{**_REQUIRED, **overrides})


class FakeProvider:
    """Captures the last message so tests can assert the effective recipient."""

    def __init__(self) -> None:
        self.sent: list = []

    @property
    def display_name(self) -> str:
        return "FakeProvider"

    def send(self, message) -> None:
        self.sent.append(message)


def _service(**overrides) -> tuple[EmailService, FakeProvider]:
    provider = FakeProvider()
    service = EmailService(settings=_settings(**overrides), provider=provider)
    return service, provider


# --------------------------------------------------------------------------
# Template engine
# --------------------------------------------------------------------------
def test_render_variable_substitution() -> None:
    assert render_template("Hello {{userName}}!", {"userName": "Alice"}) == "Hello Alice!"


def test_render_escapes_html_values() -> None:
    out = render_template("{{name}}", {"name": "<script>alert(1)</script>"})
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_each_block() -> None:
    template = "{{#each items}}<li>{{productName}} - {{lineTotal}}</li>{{/each}}"
    ctx = {
        "items": [
            {"productName": "Laptop", "lineTotal": "$1200"},
            {"productName": "Mouse", "lineTotal": "$25"},
        ]
    }
    assert render_template(template, ctx) == "<li>Laptop - $1200</li><li>Mouse - $25</li>"


def test_render_if_truthy_and_falsy() -> None:
    template = "A{{#if shippingCost}} B{{shippingCost}}{{/if}}C"
    assert render_template(template, {"shippingCost": "$10"}) == "A B$10C"
    assert render_template(template, {"shippingCost": ""}) == "AC"


def test_render_missing_variable_yields_empty() -> None:
    assert render_template("{{missing}}", {}) == ""


def test_strip_html_basic() -> None:
    html = "<p>Hello <strong>World</strong></p><br/>"
    text = strip_html(html)
    assert "Hello" in text and "World" in text


def test_app_password_normalization() -> None:
    from app.services.email_service import _normalize_app_password

    assert _normalize_app_password("abcd efgh ijkl mnop") == "abcdefghijklmnop"
    assert _normalize_app_password("  abcdefghijklmnop  ") == "abcdefghijklmnop"
    assert _normalize_app_password(None) is None
    assert _normalize_app_password("") is None


# --------------------------------------------------------------------------
# Redirect integration in the service
# --------------------------------------------------------------------------
def test_send_email_redirects_redirectable_type_in_dev() -> None:
    service, provider = _service(
        ENVIRONMENT="development",
        EMAIL_REDIRECT_ENABLED=True,
        EMAIL_REDIRECT_TO="qa-inbox@acme.com",
    )
    import asyncio

    asyncio.run(
        service.send_email(
            email_type=EmailType.ORDER_CONFIRMATION.value,
            to="buyer@acme.com",
            subject="Order Confirmation — PO-1001",
            template="order_confirmation_email",
            context={"orderNumber": "PO-1001", "orderItems": [], "totalAmount": "$1,225.00"},
        )
    )
    msg = provider.sent[-1]
    assert msg["To"] == "qa-inbox@acme.com"
    assert msg["X-S2PNexus-Redirected"] == "true"
    assert msg["X-S2PNexus-Original-To"] == "buyer@acme.com"
    assert "PO-1001" in msg.get_body(preferencelist=("html",)).get_content()


def test_welcome_email_never_redirected() -> None:
    service, provider = _service(
        ENVIRONMENT="development",
        EMAIL_REDIRECT_ENABLED=True,
        EMAIL_REDIRECT_TO="qa-inbox@acme.com",
    )
    import asyncio

    asyncio.run(
        service.send_welcome_email(
            to="new-user@acme.com",
            userName="New User",
            activationLink="https://s2pnexus.example.com/activate?token=abc",
        )
    )
    msg = provider.sent[-1]
    assert msg["To"] == "new-user@acme.com"
    assert msg["X-S2PNexus-Redirected"] == "false"


def test_password_reset_email_never_redirected() -> None:
    service, provider = _service(
        ENVIRONMENT="staging",
        EMAIL_REDIRECT_ENABLED=True,
        EMAIL_REDIRECT_TO="qa-inbox@acme.com",
    )
    import asyncio

    asyncio.run(
        service.send_password_reset_email(
            to="user@acme.com",
            userName="User",
            resetLink="https://s2pnexus.example.com/reset?token=xyz",
        )
    )
    msg = provider.sent[-1]
    assert msg["To"] == "user@acme.com"
    assert msg["X-S2PNexus-Redirected"] == "false"


def test_order_confirmation_renders_item_rows() -> None:
    service, provider = _service(
        ENVIRONMENT="development",
        EMAIL_REDIRECT_ENABLED=True,
        EMAIL_REDIRECT_TO="qa-inbox@acme.com",
    )
    import asyncio

    asyncio.run(
        service.send_order_confirmation_email(
            to="buyer@acme.com",
            userName="Buyer",
            orderNumber="PO-2001",
            orderItems=[
                {"productName": "Laptop", "sku": "SKU-1", "quantity": "1", "unitPrice": "$1,200.00", "lineTotal": "$1,200.00"},
                {"productName": "Mouse", "sku": "SKU-2", "quantity": "1", "unitPrice": "$25.00", "lineTotal": "$25.00"},
            ],
            totalAmount="$1,225.00",
        )
    )
    html = provider.sent[-1].get_body(preferencelist=("html",)).get_content()
    assert "Laptop" in html and "Mouse" in html
    assert "$1,225.00" in html


def test_email_service_uses_gmail_provider_by_default() -> None:
    service = EmailService(settings=_settings(EMAIL_PROVIDER="gmail"))
    assert service._provider.display_name == "GmailSmtpProvider"


def test_unsupported_provider_raises() -> None:
    from app.services.email_service import EmailDeliveryError

    with pytest.raises(EmailDeliveryError):
        EmailService(settings=_settings(EMAIL_PROVIDER="sendgrid"))
