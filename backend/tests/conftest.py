from __future__ import annotations

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.migrate import migrate
from app.main import app
from app.settings import settings


def _plain_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _migrated_schema():
    # Schema setup and teardown run as the admin/owner role via a raw asyncpg
    # connection -- the app's own engine connects as tenant_vault_app, which
    # deliberately cannot DROP SCHEMA, CREATE ROLE, or GRANT.
    conn = await asyncpg.connect(_plain_dsn(settings.admin_database_url))
    try:
        await conn.execute("DROP SCHEMA public CASCADE")
        await conn.execute("CREATE SCHEMA public")
    finally:
        await conn.close()
    await migrate()
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    conn = await asyncpg.connect(_plain_dsn(settings.admin_database_url))
    try:
        await conn.execute("TRUNCATE organizations, users, records, audit_log, webhook_events, jobs CASCADE")
    finally:
        await conn.close()
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
