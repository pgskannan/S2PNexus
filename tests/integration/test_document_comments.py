"""Document comment threads for PR and PO (shared tab behavior).

Covers the acceptance criteria for the Comments tab: adding a comment on a PR
and on a PO, listing them back, and ensuring PR/PO comments never
cross-contaminate (a PO comment must not appear under the PR and vice versa).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

USER_ID = uuid.UUID(int=(2**128 - 1))  # matches conftest auth override
SUPPLIER_ID = uuid.UUID(int=(2**128 - 2))


@pytest.mark.asyncio
async def test_pr_and_po_comment_threads(client, db_session):
    # 1. Create a requisition.
    r = await client.post(
        "/api/v1/procurement/requisitions",
        json={
            "title": "Comments PR",
            "requested_by": str(USER_ID),
            "supplier_id": str(SUPPLIER_ID),
            "currency": "USD",
        },
    )
    assert r.status_code == 201, r.text
    pr_id = r.json()["id"]

    # 2. Add a comment to the PR.
    r = await client.post(
        f"/api/v1/procurement/requisitions/{pr_id}/comments",
        json={"comment": "Please expedite this request"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["comment"] == "Please expedite this request"
    assert r.json()["requisition_id"] == pr_id
    assert r.json()["purchase_order_id"] is None

    # 3. List PR comments.
    r = await client.get(f"/api/v1/procurement/requisitions/{pr_id}/comments")
    assert r.status_code == 200, r.text
    pr_comments = r.json()
    assert len(pr_comments) == 1
    assert pr_comments[0]["comment"] == "Please expedite this request"

    # 4. Submit then approve -> auto-creates the PO.
    r = await client.post(
        f"/api/v1/procurement/requisitions/{pr_id}/transition",
        json={"new_status": "submitted", "lifecycle_status": "submitted"},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/procurement/requisitions/{pr_id}/transition",
        json={"new_status": "approved", "lifecycle_status": "approved"},
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/procurement/purchase-orders?requisition_id={pr_id}")
    assert r.status_code == 200, r.text
    po_items = r.json()["items"]
    assert len(po_items) == 1, r.text
    po_id = po_items[0]["id"]

    # 5. Add a comment to the PO.
    r = await client.post(
        f"/api/v1/procurement/purchase-orders/{po_id}/comments",
        json={"comment": "Supplier confirmed delivery window"},
    )
    assert r.status_code == 201, r.text
    po_comment = r.json()
    assert po_comment["comment"] == "Supplier confirmed delivery window"
    assert po_comment["purchase_order_id"] == po_id
    assert po_comment["requisition_id"] is None

    # 6. List PO comments -- only the PO comment.
    r = await client.get(f"/api/v1/procurement/purchase-orders/{po_id}/comments")
    assert r.status_code == 200, r.text
    po_comments = r.json()
    assert len(po_comments) == 1
    assert po_comments[0]["comment"] == "Supplier confirmed delivery window"

    # 7. No cross-contamination: the PR thread must still show only its own
    # comment, and the PO thread only its own.
    r = await client.get(f"/api/v1/procurement/requisitions/{pr_id}/comments")
    assert r.status_code == 200, r.text
    pr_comments = r.json()
    assert len(pr_comments) == 1
    assert all(c["purchase_order_id"] is None for c in pr_comments)

    r = await client.get(f"/api/v1/procurement/purchase-orders/{po_id}/comments")
    assert r.status_code == 200, r.text
    po_comments = r.json()
    assert len(po_comments) == 1
    assert all(c["requisition_id"] is None for c in po_comments)

    # 8. Persistence: the rows are in the database (not just the response).
    from sqlalchemy import select

    from app.models.procurement import ProcurementComment

    stored = (await db_session.execute(select(ProcurementComment))).scalars().all()
    assert len(stored) == 2
