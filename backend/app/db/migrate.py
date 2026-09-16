from __future__ import annotations

from pathlib import Path

import asyncpg

from ..settings import settings


async def migrate() -> None:
    """
    Applies every file in sql/ in name order, via a raw asyncpg connection
    rather than through SQLAlchemy: asyncpg's simple query protocol executes
    a whole file of semicolon-separated DDL (including CREATE POLICY, which
    SQLAlchemy's async engine does not reliably batch) in one call.
    """
    dsn = settings.admin_database_url.replace("postgresql+asyncpg://", "postgresql://")
    sql_dir = Path(__file__).resolve().parents[2] / "sql"
    conn = await asyncpg.connect(dsn)
    try:
        for path in sorted(sql_dir.glob("*.sql")):
            await conn.execute(path.read_text())
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(migrate())
