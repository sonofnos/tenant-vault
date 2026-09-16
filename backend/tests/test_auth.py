from __future__ import annotations

import pytest

from tests.helpers import signup_and_login


@pytest.mark.asyncio
async def test_signup_rejects_duplicate_org_slug(client):
    await signup_and_login(client, "acme")
    resp = await client.post("/auth/signup", json={"organization_name": "Acme Again", "organization_slug": "acme", "email": "other@example.com", "password": "correct-horse-battery"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_signup_rejects_an_invalid_slug(client):
    resp = await client.post("/auth/signup", json={"organization_name": "Acme", "organization_slug": "Not Valid!", "email": "a@example.com", "password": "correct-horse-battery"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_fails_for_unknown_org_slug(client):
    resp = await client.post("/auth/login", json={"organization_slug": "does-not-exist", "email": "a@example.com", "password": "correct-horse-battery"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_fails_for_correct_email_wrong_org(client):
    """Same email could plausibly exist in another org's user table; logging in against the wrong org must fail rather than accidentally matching cross-tenant."""
    await signup_and_login(client, "org-a", email="shared@example.com")
    await signup_and_login(client, "org-b", email="different@example.com")

    resp = await client.post("/auth/login", json={"organization_slug": "org-b", "email": "shared@example.com", "password": "correct-horse-battery"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_token_is_rejected(client):
    resp = await client.get("/records")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_malformed_token_is_rejected(client):
    resp = await client.get("/records", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
