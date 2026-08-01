"""Email redirect smoke test — sends real emails via the configured SMTP provider.

Usage (from repo root, after filling EMAIL_PASSWORD in .env):
    c:/S2PNexus/.venv/Scripts/python.exe scripts/email_smoke_test.py

What it verifies (Email Redirect spec §6.3):
  1. REDIRECTABLE (order confirmation) sent to a non-existing buyer address is
     delivered to EMAIL_REDIRECT_TO with header X-S2PNexus-Redirected: true.
  2. NON-REDIRECTABLE (welcome) is delivered directly to the recipient with
     header X-S2PNexus-Redirected: false.

Never prints the SMTP password.
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import get_settings
from app.middleware.email_redirect import EmailType
from app.services.email_service import EmailService


def main() -> int:
    settings = get_settings()

    if not (settings.EMAIL_USERNAME and (settings.EMAIL_PASSWORD or settings.SMTP_PASSWORD)):
        print("ERROR: EMAIL_USERNAME / EMAIL_PASSWORD not set in .env (App Password required).")
        return 2

    if not settings.email_redirect_active:
        print("WARNING: EMAIL_REDIRECT is not active "
              "(EMAIL_REDIRECT_ENABLED and non-production ENVIRONMENT required).")

    service = EmailService(settings=settings)
    redirect_to = settings.EMAIL_REDIRECT_TO or settings.EMAIL_USERNAME
    fake_buyer = "buyer@example.invalid"  # never a real mailbox

    async def run() -> None:
        # 1) Redirectable: order confirmation to a fake buyer -> must land in the redirect inbox.
        result = await service.send_order_confirmation_email(
            to=fake_buyer,
            userName="QA Smoke Test",
            orderNumber="PO-SMOKE-2026",
            orderItems=[
                {"productName": "QA Laptop", "sku": "QA-1", "quantity": "1",
                 "unitPrice": "$1,299.00", "lineTotal": "$1,299.00"},
                {"productName": "QA Docking Station", "sku": "QA-2", "quantity": "1",
                 "unitPrice": "$89.00", "lineTotal": "$89.00"},
            ],
            totalAmount="$1,388.00",
        )
        assert result.redirected is True, "order confirmation should be redirected"
        assert result.effective_recipient == redirect_to
        print(f"[1] REDIRECTED  ok  -> {result.effective_recipient} "
              f"(original {result.original_recipient}) type={result.email_type}")

        # 2) Non-redirectable: welcome to the real inbox -> must NOT be redirected.
        welcome = await service.send_welcome_email(
            to=redirect_to,  # acting as the real new user
            userName="QA New User",
            activationLink="https://s2pnexus.example.com/activate?token=smoke",
        )
        assert welcome.redirected is False, "welcome email must never be redirected"
        assert welcome.effective_recipient == redirect_to
        print(f"[2] WELCOME direct ok -> {welcome.effective_recipient} "
              f"(never redirected) type={welcome.email_type}")

    try:
        asyncio.run(run())
    except Exception as exc:  # noqa: BLE001 - report delivery failure cleanly
        print(f"SMOKE TEST FAILED: {exc}")
        return 1

    print("SMOKE TEST PASSED — check pgskannan@gmail.com inbox for both emails.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
