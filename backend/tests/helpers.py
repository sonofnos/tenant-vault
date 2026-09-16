from __future__ import annotations

from httpx import AsyncClient


async def signup_and_login(client: AsyncClient, org_slug: str, email: str = "admin@example.com", password: str = "correct-horse-battery") -> str:
    resp = await client.post("/auth/signup", json={"organization_name": org_slug.title(), "organization_slug": org_slug, "email": email, "password": password})
    assert resp.status_code == 201, resp.text
    login = await client.post("/auth/login", json={"organization_slug": org_slug, "email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
