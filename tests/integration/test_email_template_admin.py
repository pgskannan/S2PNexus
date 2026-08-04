"""Integration tests for admin-configurable email templates (backlog Section 1).

Covers the new /admin/email-templates router (list / get / put, gated by the
admin role check) plus the send-path wiring: an active override for
``po.dispatch`` changes the subject/footer/logo of the PO dispatch email
without touching the redirect pipeline. Follows the house style: real HTTP
calls through the FastAPI test client, real in-memory SQLite, no mocking of
the code under test (only the SMTP transport is stubbed, as the existing
unit tests do).
"""

from __future__ import annotations

import uuid

import pytest

from app.main import app
from app.models.user import UserRole
from app.services.email_service import EmailService

USER_ID = uuid.UUID(int=(2**128 - 1))  # matches conftest auth override


class FakeProvider:
    """Captures messages so tests can assert rendered content."""

    def __init__(self) -> None:
        self.sent: list = []

    @property
    def display_name(self) -> str:
        return "FakeProvider"

    def send(self, message) -> None:
        self.sent.append(message)


def _html(msg) -> str:
    return msg.get_body(preferencelist=("html",)).get_content()


# --------------------------------------------------------------------------
# Admin router
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_email_templates_returns_catalog(client, db_session):
    r = await client.get("/api/v1/admin/email-templates")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] > 0
    types = {item["email_type"] for item in body["items"]}
    assert "po.dispatch" in types
    po = next(item for item in body["items"] if item["email_type"] == "po.dispatch")
    assert po["module"] == "PO"
    assert po["has_override"] is False
    assert po["subject"]  # catalog default always present


@pytest.mark.asyncio
async def test_get_unknown_email_type_404(client):
    r = await client.get("/api/v1/admin/email-templates/does.not.exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_override_then_get_reflects(client, db_session):
    r = await client.put(
        "/api/v1/admin/email-templates/po.dispatch",
        json={
            "subject_override": "ACME PO {{poNumber}} — Custom Subject",
            "footer_override": "ACME Procurement, 100 Main St, Anytown",
            "branding_logo_url": "https://example.com/acme-logo.png",
            "is_active": True,
        },
    )
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["email_type"] == "po.dispatch"
    assert saved["subject_override"].startswith("ACME PO")

    r = await client.get("/api/v1/admin/email-templates/po.dispatch")
    assert r.status_code == 200
    entry = r.json()["entry"]
    assert entry["has_override"] is True
    assert entry["footer_override"] == "ACME Procurement, 100 Main St, Anytown"
    assert entry["branding_logo_url"] == "https://example.com/acme-logo.png"
    assert entry["override_active"] is True

    # List view also shows the merged override.
    r = await client.get("/api/v1/admin/email-templates")
    po = next(item for item in r.json()["items"] if item["email_type"] == "po.dispatch")
    assert po["has_override"] is True
    assert po["subject_override"].startswith("ACME PO")


@pytest.mark.asyncio
async def test_put_unknown_email_type_404(client):
    r = await client.put(
        "/api/v1/admin/email-templates/not.real",
        json={"subject_override": "nope", "is_active": True},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_inactive_override_falls_back_to_catalog(client, db_session):
    r = await client.put(
        "/api/v1/admin/email-templates/po.dispatch",
        json={"subject_override": "IGNORED", "is_active": False},
    )
    assert r.status_code == 200

    # Inactive override still shown in the admin detail (so it can be
    # re-activated), but it is NOT applied at send time (tested below).
    r = await client.get("/api/v1/admin/email-templates/po.dispatch")
    assert r.json()["entry"]["has_override"] is True
    assert r.json()["entry"]["override_active"] is False


# --------------------------------------------------------------------------
# Non-admin gate
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_non_admin_forbidden(client):
    from types import SimpleNamespace

    from app.utils.dependencies import get_current_active_user

    async def override_user():
        return SimpleNamespace(
            id=USER_ID,
            email="requester@example.com",
            full_name="Requester",
            role=UserRole.REQUESTER,
            is_active=True,
            is_superuser=False,
            tenant_id=None,
        )

    # The client fixture clears dependency overrides on teardown, so no
    # manual restore is needed.
    app.dependency_overrides[get_current_active_user] = override_user

    r = await client.get("/api/v1/admin/email-templates")
    assert r.status_code == 403
    r = await client.put("/api/v1/admin/email-templates/po.dispatch", json={"is_active": True})
    assert r.status_code == 403


# --------------------------------------------------------------------------
# Send-path wiring: override changes content, not delivery
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_purchase_order_email_uses_override(client, db_session):
    from app.core.config import get_settings

    r = await client.put(
        "/api/v1/admin/email-templates/po.dispatch",
        json={
            "subject_override": "ACME Dispatch {{poNumber}}",
            "footer_override": "ACME Footer Line",
            "branding_logo_url": "https://example.com/logo.png",
            "is_active": True,
        },
    )
    assert r.status_code == 200, r.text

    provider = FakeProvider()
    service = EmailService(settings=get_settings(), provider=provider)
    await service.send_purchase_order_email(
        to="supplier@acme.com",
        poNumber="PO-1001",
        companyName="ACME",
        poDate="2026-08-04",
    )

    assert provider.sent, "expected a captured message"
    msg = provider.sent[-1]
    assert "ACME Dispatch PO-1001" in msg["Subject"]
    body = _html(msg)
    assert "ACME Footer Line" in body
    assert "https://example.com/logo.png" in body


@pytest.mark.asyncio
async def test_send_purchase_order_email_without_override_uses_default(client, db_session):
    from app.core.config import get_settings

    provider = FakeProvider()
    service = EmailService(settings=get_settings(), provider=provider)
    await service.send_purchase_order_email(
        to="supplier@acme.com",
        poNumber="PO-2002",
        companyName="ACME",
        poDate="2026-08-04",
    )

    assert provider.sent
    msg = provider.sent[-1]
    assert "PO-2002" in msg["Subject"]
    assert "PO-2002" in _html(msg)


@pytest.mark.asyncio
async def test_inactive_override_not_applied_at_send(client, db_session):
    from app.core.config import get_settings

    await client.put(
        "/api/v1/admin/email-templates/po.dispatch",
        json={"subject_override": "SHOULD NOT SHOW", "is_active": False},
    )

    provider = FakeProvider()
    service = EmailService(settings=get_settings(), provider=provider)
    await service.send_purchase_order_email(to="supplier@acme.com", poNumber="PO-3003")

    assert provider.sent
    msg = provider.sent[-1]
    assert "SHOULD NOT SHOW" not in msg["Subject"]


@pytest.mark.asyncio
async def test_override_does_not_change_redirect_recipient(client, db_session):
    """Overrides change content only — the redirect pipeline is untouched."""
    from app.core.config import get_settings

    await client.put(
        "/api/v1/admin/email-templates/po.dispatch",
        json={"subject_override": "ACME Redirect Check {{poNumber}}", "is_active": True},
    )

    provider = FakeProvider()
    settings = get_settings().model_copy(
        update={
            "ENVIRONMENT": "development",
            "EMAIL_REDIRECT_ENABLED": True,
            "EMAIL_REDIRECT_TO": "qa-inbox@acme.com",
        }
    )
    service = EmailService(settings=settings, provider=provider)
    await service.send_purchase_order_email(to="supplier@acme.com", poNumber="PO-4004")

    assert provider.sent
    msg = provider.sent[-1]
    assert msg["To"] == "qa-inbox@acme.com"
    assert msg["X-S2PNexus-Redirected"] == "true"
    assert "ACME Redirect Check PO-4004" in msg["Subject"]
