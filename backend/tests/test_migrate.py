from __future__ import annotations

import asyncpg
import pytest

from app.db.migrate import _asyncpg_dsn, migrate
from app.settings import settings


@pytest.mark.asyncio
async def test_migrate_is_safe_to_run_on_every_deploy():
    await migrate()
    await migrate()

    conn = await asyncpg.connect(_asyncpg_dsn(settings.admin_database_url))
    try:
        applied = [r["filename"] for r in await conn.fetch("SELECT filename FROM schema_migrations ORDER BY filename")]
    finally:
        await conn.close()
    assert applied == ["001_schema.sql", "002_grants.sql"]


def test_ssl_query_param_is_translated_for_raw_asyncpg():
    url = "postgresql+asyncpg://u:p@host/db?ssl=require"
    assert _asyncpg_dsn(url) == "postgresql://u:p@host/db?sslmode=require"
