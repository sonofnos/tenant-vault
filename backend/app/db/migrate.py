from __future__ import annotations

from pathlib import Path

import asyncpg

from ..settings import settings

# Idempotent and re-applied on every run, so a changed APP_DB_PASSWORD reaches the role.
ALWAYS_RUN = {"000_app_role.sql"}


def _asyncpg_dsn(url: str) -> str:
    # SQLAlchemy's asyncpg dialect takes ?ssl=require; a raw asyncpg DSN wants sslmode.
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("ssl=", "sslmode=")


async def migrate() -> None:
    """
    Applies sql/ files in name order via a raw asyncpg connection (its simple
    query protocol runs a whole file of DDL, including CREATE POLICY, in one
    call). Each schema file is recorded in schema_migrations and applied once,
    in the same transaction as its record, so a deploy can run this on every start.
    """
    sql_dir = Path(__file__).resolve().parents[2] / "sql"
    conn = await asyncpg.connect(_asyncpg_dsn(settings.admin_database_url))
    try:
        await conn.execute("SELECT set_config('tenant_vault.app_password', $1, false)", settings.app_db_password)
        await conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        applied = {r["filename"] for r in await conn.fetch("SELECT filename FROM schema_migrations")}

        for path in sorted(sql_dir.glob("*.sql")):
            if path.name in ALWAYS_RUN:
                await conn.execute(path.read_text())
                continue
            if path.name in applied:
                continue
            async with conn.transaction():
                await conn.execute(path.read_text())
                await conn.execute("INSERT INTO schema_migrations (filename) VALUES ($1)", path.name)
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(migrate())
