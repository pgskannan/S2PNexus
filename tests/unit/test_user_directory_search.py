"""Regression guard for GET /users/directory's new `search` param.

Requested 2026-08-01: UserPicker.tsx (used by the approver-matrix admin page
and the workflow designer's approver/escalate-to fields) was calling GET
/users (superuser-only) instead of GET /users/directory (any authenticated
user). For an admin whose account has role=administrator but
is_superuser=False, that 403'd and the picker's catch-all silently showed
"No matches" -- looked exactly like "not able to add users." Fixed by
switching UserPicker to /users/directory and giving it the `search` param it
needs for the picker's search-as-you-type UX to actually narrow results
(previously /directory only took `limit`, no filtering at all).
"""

from __future__ import annotations

import uuid

import pytest

from app.core.security import get_password_hash
from app.models.user import User, UserRole


async def _make_user(db_session, *, email: str, full_name: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name=full_name,
        hashed_password=get_password_hash("Test1234!"),
        role=UserRole.REQUESTER,
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_directory_search_filters_by_name(client, db_session):
    await _make_user(db_session, email="alice.searchtest@example.com", full_name="Alice Searchtest")
    await _make_user(db_session, email="bob.other@example.com", full_name="Bob Other")

    response = await client.get("/api/v1/users/directory", params={"search": "Searchtest"})
    assert response.status_code == 200
    names = {item["full_name"] for item in response.json()["items"]}
    assert "Alice Searchtest" in names
    assert "Bob Other" not in names


@pytest.mark.asyncio
async def test_directory_search_matches_email_too(client, db_session):
    await _make_user(db_session, email="carol.uniqueemailtest@example.com", full_name="Carol Someone")

    response = await client.get("/api/v1/users/directory", params={"search": "uniqueemailtest"})
    assert response.status_code == 200
    emails = {item["email"] for item in response.json()["items"]}
    assert "carol.uniqueemailtest@example.com" in emails


@pytest.mark.asyncio
async def test_directory_entry_excludes_sensitive_fields(client, db_session):
    await _make_user(db_session, email="dave.fieldscopetest@example.com", full_name="Dave Fieldscopetest")

    response = await client.get("/api/v1/users/directory", params={"search": "Fieldscopetest"})
    assert response.status_code == 200
    entry = response.json()["items"][0]
    assert set(entry.keys()) == {"id", "full_name", "email"}
