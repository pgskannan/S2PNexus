#!/usr/bin/env python3
"""S2PNexus end-to-end procurement lifecycle demo.

Walks the full flow against a live S2PNexus API (Cloud Run):

    login -> PR -> line item -> submit -> approve -> PO -> ordered -> receipt
    (submit/approve/post) -> invoice -> 3-way match -> GR/IR -> block status ->
    OK-to-Pay.

Requirements: `pip install httpx` (already in backend/requirements.txt).

USAGE
-----
    # Against the deployed Cloud Run backend with an existing user:
    set S2P_BASE_URL=https://s2pnexus-backend-120737021520.us-central1.run.app
    set S2P_EMAIL=you@example.com
    set S2P_PASSWORD=YourPassword

    python scripts/end_to_end_demo.py

    # Or skip login entirely and pass a bearer token:
    set S2P_TOKEN=<jwt>
    python scripts/end_to_end_demo.py

The script ensures a 3-way matching policy exists for the demo commodity
(10010103) so the PO auto-drafts a receipt and auto-closes; the upload endpoint
is idempotent (upserts), and requires the API user to be an administrator.

A 3-way policy is REQUIRED for the receipt/auto-close leg; if your user cannot
upload master data, pre-load it via Settings > Master Data > Matching Policy
(scenario_matching_policies.csv from scripts/seed_data/).
"""

from __future__ import annotations

import os
import sys
import uuid

import httpx

DEFAULT_BASE_URL = "https://s2pnexus-backend-120737021520.us-central1.run.app"
BASE_URL = os.environ.get("S2P_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
EMAIL = os.environ.get("S2P_EMAIL")
PASSWORD = os.environ.get("S2P_PASSWORD")
TOKEN = os.environ.get("S2P_TOKEN")

COMMODITY_CODE = "10010103"
POLICY_CSV = (
    "scope_level,scope_code,required_match_type,auto_receive,auto_receive_price_threshold\n"
    f"commodity,{COMMODITY_CODE},three_way,false,\n"
)


def log(step: str, status: int, body) -> None:
    preview = body if isinstance(body, str) else str(body)
    if len(preview) > 220:
        preview = preview[:220] + "..."
    print(f"[{status}] {step}: {preview}")


def get_token(client: httpx.Client) -> str:
    if TOKEN:
        return TOKEN
    if not EMAIL or not PASSWORD:
        print("Set S2P_TOKEN or S2P_EMAIL + S2P_PASSWORD.", file=sys.stderr)
        sys.exit(2)
    r = client.post(f"{BASE_URL}/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> int:
    with httpx.Client(timeout=60.0) as client:
        token = get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        # 0. Ensure a 3-way matching policy exists for the demo commodity.
        r = client.post(
            f"{BASE_URL}/api/v1/commodity/policies/upload",
            headers=headers,
            files={"file": ("matching_policies.csv", POLICY_CSV, "text/csv")},
        )
        log("Ensure 3-way matching policy", r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)

        supplier_id = str(uuid.uuid4())

        # 1. Create PR.
        r = client.post(
            f"{BASE_URL}/api/v1/procurement/requisitions",
            headers=headers,
            json={"title": "E2E Widget PR", "requested_by": _user_id(client, headers), "supplier_id": supplier_id, "currency": "USD"},
        )
        r.raise_for_status()
        pr_id = r.json()["id"]
        log("PR created", r.status_code, pr_id)

        # 2. Add a line item on the 3-way commodity.
        r = client.post(
            f"{BASE_URL}/api/v1/procurement/requisitions/{pr_id}/line-items",
            headers=headers,
            json={"description": "Widget", "quantity": "10", "unit_price": "5.00", "category": "IT", "commodity": COMMODITY_CODE},
        )
        r.raise_for_status()
        log("Line item added", r.status_code, r.json()["id"])

        # 3. Submit + approve (auto-creates the PO).
        for lifecycle in ("submitted", "approved"):
            r = client.post(
                f"{BASE_URL}/api/v1/procurement/requisitions/{pr_id}/transition",
                headers=headers,
                json={"new_status": lifecycle, "lifecycle_status": lifecycle},
            )
            r.raise_for_status()
            log(f"PR -> {lifecycle}", r.status_code, r.json().get("lifecycle_status"))

        # 4. Fetch the auto-created PO.
        r = client.get(f"{BASE_URL}/api/v1/procurement/purchase-orders?requisition_id={pr_id}", headers=headers)
        r.raise_for_status()
        items = r.json()["items"]
        assert items, "no PO was auto-created"
        po = items[0]
        po_id, po_line_id = po["id"], po["line_items"][0]["id"]
        log("PO auto-created", r.status_code, po_id)

        # 5. Move the PO through approval to Ordered.
        for lifecycle in ("pending_approval", "approved", "ordered"):
            r = client.post(
                f"{BASE_URL}/api/v1/procurement/purchase-orders/{po_id}/lifecycle/transition",
                headers=headers,
                json={"lifecycle_status": lifecycle},
            )
            r.raise_for_status()
            log(f"PO -> {lifecycle}", r.status_code, r.json().get("lifecycle_status"))

        # 6. Manually receive the full quantity.
        r = client.post(
            f"{BASE_URL}/api/v1/procurement/purchase-orders/{po_id}/receipts",
            headers=headers,
            json={
                "line_items": [
                    {"purchase_order_line_item_id": po_line_id, "quantity_received": "10", "quantity_rejected": "0"}
                ]
            },
        )
        r.raise_for_status()
        receipt_id = r.json()["id"]
        log("Receipt created", r.status_code, receipt_id)

        # 7. Receipt workflow: submit -> approve -> post.
        for action in ("submit", "approve", "post"):
            r = client.post(f"{BASE_URL}/api/v1/procurement/receipts/{receipt_id}/{action}", headers=headers)
            r.raise_for_status()
            log(f"Receipt -> {action}", r.status_code, r.json().get("status"))

        # 8. Create a fully-matching invoice.
        r = client.post(
            f"{BASE_URL}/api/v1/procurement/invoices",
            headers=headers,
            json={
                "supplier_id": supplier_id,
                "purchase_order_id": po_id,
                "amount": "50.00",
                "total_amount": "50.00",
                "line_items": [
                    {
                        "purchase_order_line_item_id": po_line_id,
                        "description": "Widget",
                        "quantity": "10",
                        "unit_price": "5.00",
                        "line_total": "50.00",
                    }
                ],
            },
        )
        r.raise_for_status()
        invoice_id = r.json()["id"]
        log("Invoice created", r.status_code, invoice_id)

        # 9. 3-way match.
        r = client.post(
            f"{BASE_URL}/api/v1/procurement/invoices/{invoice_id}/match", headers=headers, json={"match_type": "three_way"}
        )
        r.raise_for_status()
        log("Invoice matched", r.status_code, r.json().get("match_status"))

        # 10. GR/IR status.
        r = client.get(f"{BASE_URL}/api/v1/procurement/purchase-orders/{po_id}/grir", headers=headers)
        r.raise_for_status()
        log("GR/IR", r.status_code, [x["status"] for x in r.json()])

        # 11. Match result.
        r = client.get(f"{BASE_URL}/api/v1/procurement/invoices/{invoice_id}/match-result", headers=headers)
        r.raise_for_status()
        log("Match result", r.status_code, r.json().get("overall_status"))

        # 12. Block status.
        r = client.get(f"{BASE_URL}/api/v1/procurement/invoices/{invoice_id}/block", headers=headers)
        r.raise_for_status()
        log("Block status", r.status_code, r.json().get("block_status"))

        # 13. OK-to-Pay.
        r = client.post(
            f"{BASE_URL}/api/v1/procurement/ok-to-pay/generate",
            headers=headers,
            json={
                "invoice_ids": [invoice_id],
                "supplier_id": supplier_id,
                "payment_batch": "PAY-E2E-001",
                "payment_date": "2026-07-31",
                "payment_completed": True,
            },
        )
        r.raise_for_status()
        body = r.json()
        log("OK-to-Pay", r.status_code, {"ok": body.get("ok"), "rows": len(body.get("rows", []))})

        print("\nE2E demo completed successfully.")
        return 0


def _user_id(client: httpx.Client, headers: dict) -> str:
    """Best-effort: the authenticated user's id (used as PR requested_by)."""
    r = client.get(f"{BASE_URL}/api/v1/auth/me", headers=headers)
    if r.status_code == 200:
        return r.json().get("id", str(uuid.UUID(int=(2**128 - 1))))
    return str(uuid.UUID(int=(2**128 - 1)))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPStatusError as exc:
        print(f"\nHTTP error at {exc.request.url}: {exc.response.status_code} {exc.response.text[:500]}", file=sys.stderr)
        raise SystemExit(1)
    except AssertionError as exc:
        print(f"\nE2E assertion failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
