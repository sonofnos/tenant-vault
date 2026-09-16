from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.session import tenant_session
from tests.helpers import auth_headers, signup_and_login


async def _add_member(client, org_slug: str, email: str, role_name: str) -> str:
    """No signup endpoint issues non-admin roles (signup always creates an admin), so tests seed a member/viewer directly -- the same shape a real invite-a-teammate endpoint would insert through."""
    from app.auth.security import hash_password

    admin_token = await signup_and_login(client, org_slug)
    import jwt as pyjwt

    from app.settings import settings

    org_id = pyjwt.decode(admin_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])["org_id"]

    role_id = {"admin": 1, "member": 2, "viewer": 3}[role_name]
    async with tenant_session(org_id) as session:
        await session.execute(
            text("INSERT INTO users (org_id, email, password_hash, role_id) VALUES (:org_id, :email, :hash, :role_id)"),
            {"org_id": org_id, "email": email, "hash": hash_password("correct-horse-battery"), "role_id": role_id},
        )
    login = await client.post("/auth/login", json={"organization_slug": org_slug, "email": email, "password": "correct-horse-battery"})
    return login.json()["access_token"], admin_token


@pytest.mark.asyncio
async def test_viewer_cannot_create_a_record(client):
    viewer_token, _ = await _add_member(client, "org-a", "viewer@example.com", "viewer")
    res = await client.post("/records", json={"subject_name": "Alice", "notes": "n"}, headers=auth_headers(viewer_token))
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_viewer_can_read_records(client):
    viewer_token, admin_token = await _add_member(client, "org-a", "viewer@example.com", "viewer")
    await client.post("/records", json={"subject_name": "Alice", "notes": "n"}, headers=auth_headers(admin_token))
    res = await client.get("/records", headers=auth_headers(viewer_token))
    assert res.status_code == 200
    assert len(res.json()) == 1


@pytest.mark.asyncio
async def test_member_can_create_but_not_delete(client):
    member_token, _ = await _add_member(client, "org-a", "member@example.com", "member")
    created = await client.post("/records", json={"subject_name": "Alice", "notes": "n"}, headers=auth_headers(member_token))
    assert created.status_code == 201

    delete = await client.delete(f"/records/{created.json()['id']}", headers=auth_headers(member_token))
    assert delete.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_delete(client):
    admin_token = await signup_and_login(client, "org-a")
    created = await client.post("/records", json={"subject_name": "Alice", "notes": "n"}, headers=auth_headers(admin_token))
    delete = await client.delete(f"/records/{created.json()['id']}", headers=auth_headers(admin_token))
    assert delete.status_code == 204


@pytest.mark.asyncio
async def test_deleting_and_status_changes_are_audited(client):
    admin_token = await signup_and_login(client, "org-a")
    created = await client.post("/records", json={"subject_name": "Alice", "notes": "n"}, headers=auth_headers(admin_token))
    record_id = created.json()["id"]
    await client.patch(f"/records/{record_id}/status", json={"status": "reviewed"}, headers=auth_headers(admin_token))
    await client.delete(f"/records/{record_id}", headers=auth_headers(admin_token))

    import jwt as pyjwt

    from app.settings import settings

    org_id = pyjwt.decode(admin_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])["org_id"]
    async with tenant_session(org_id) as session:
        actions = (await session.execute(text("SELECT action FROM audit_log ORDER BY id"))).scalars().all()
    assert actions == ["record.created", "record.status_changed", "record.deleted"]
