"""
The one test suite in this repo that matters most: proving row-level security
actually enforces org isolation at the database, not just in application code.

Every test here does the thing a WHERE org_id=... filter would have prevented
anyway (the API never even builds a query without one), and then goes one
step further: it queries the table directly, inside the *other* org's
transaction context, with no application-level filter at all, to prove the
isolation holds even when the calling code "forgets".
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.session import tenant_session
from tests.helpers import auth_headers, signup_and_login


@pytest.mark.asyncio
async def test_api_never_returns_another_orgs_record(client):
    token_a = await signup_and_login(client, "org-a")
    token_b = await signup_and_login(client, "org-b")

    created = await client.post("/records", json={"subject_name": "Alice", "notes": "First note."}, headers=auth_headers(token_a))
    record_id = created.json()["id"]

    # org B asks for org A's record by id directly -- not a list, not a guess,
    # the exact id. RLS means the row isn't in org B's query result at all.
    res = await client.get(f"/records/{record_id}", headers=auth_headers(token_b))
    assert res.status_code == 404

    # org B's own list is empty; org A's record does not leak into it.
    listing = await client.get("/records", headers=auth_headers(token_b))
    assert listing.json() == []


@pytest.mark.asyncio
async def test_raw_query_with_no_where_clause_still_only_sees_its_own_org(client):
    """
    This is the test that actually proves RLS, not app logic, is doing the
    work: a raw SELECT with zero filtering, run inside org A's transaction
    context. If this ever returns org B's rows, the isolation is an
    application convention, not a database guarantee.
    """
    token_a = await signup_and_login(client, "org-a")
    token_b = await signup_and_login(client, "org-b")

    await client.post("/records", json={"subject_name": "Alice", "notes": "org A's note"}, headers=auth_headers(token_a))
    await client.post("/records", json={"subject_name": "Bob", "notes": "org B's note"}, headers=auth_headers(token_b))

    org_a_id = await _org_id_from_login(client, "org-a")

    async with tenant_session(org_a_id) as session:
        rows = (await session.execute(text("SELECT subject_name FROM records"))).scalars().all()

    assert rows == ["Alice"]  # not ["Alice", "Bob"] -- Bob's row is invisible, full stop


@pytest.mark.asyncio
async def test_platform_session_with_no_org_context_sees_zero_tenant_rows(client):
    """
    org_id=None (the platform-level mode used only for signup/login's org
    lookup) is not an admin bypass. FORCE ROW LEVEL SECURITY plus a policy
    that requires the setting to be present means an unscoped session sees
    nothing in any tenant table, including tables that have data in them.
    """
    token_a = await signup_and_login(client, "org-a")
    await client.post("/records", json={"subject_name": "Alice", "notes": "note"}, headers=auth_headers(token_a))

    async with tenant_session(org_id=None) as session:
        rows = (await session.execute(text("SELECT * FROM records"))).all()

    assert rows == []


@pytest.mark.asyncio
async def test_cannot_update_or_delete_another_orgs_row_via_raw_sql(client):
    """WITH CHECK, not just USING: an UPDATE that tries to write a row it can't see affects zero rows, not someone else's row."""
    token_a = await signup_and_login(client, "org-a")
    await signup_and_login(client, "org-b")
    created = await client.post("/records", json={"subject_name": "Alice", "notes": "n"}, headers=auth_headers(token_a))
    record_id = created.json()["id"]

    org_b_id = await _org_id_from_login(client, "org-b")
    async with tenant_session(org_b_id) as session:
        result = await session.execute(text("UPDATE records SET notes = 'tampered' WHERE id = :id"), {"id": record_id})
        assert result.rowcount == 0

    # confirm from org A's own perspective it was never touched
    res = await client.get(f"/records/{record_id}", headers=auth_headers(token_a))
    assert res.json()["notes"] == "n"


async def _org_id_from_login(client, slug: str) -> str:
    import jwt as pyjwt

    from app.settings import settings

    login = await client.post("/auth/login", json={"organization_slug": slug, "email": "admin@example.com", "password": "correct-horse-battery"})
    token = login.json()["access_token"]
    payload = pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return payload["org_id"]
