from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ..settings import settings

# NullPool: a fresh asyncpg connection per checkout rather than a pooled one.
# In production this trades a little connection-setup latency for one less
# thing to reason about; in the test suite it's what stops connections from
# a previous test's event loop being handed to the next test's loop, which
# asyncpg refuses outright ("attached to a different loop").
engine = create_async_engine(settings.database_url, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def tenant_session(org_id: UUID | None) -> AsyncIterator[AsyncSession]:
    """
    Every request that touches tenant data opens its session through here, not
    through SessionLocal directly.

    `set_config('app.current_org_id', ..., true)` sets a *transaction-local*
    Postgres setting (the `true` third argument is what makes it transaction-
    scoped rather than session-scoped) that every RLS policy in this schema
    reads via `current_setting('app.current_org_id')`. Because it's set inside
    the same transaction as every query that follows, there is no window where
    a connection pulled from the pool could still be carrying a *previous*
    request's org id -- the setting does not outlive the transaction, and every
    request gets its own transaction.

    `org_id=None` is for platform-level operations only (the row that creates
    an organization itself, before any org-scoped user or record can exist)
    and deliberately does not set the RLS variable at all, which means the
    RLS policies -- which require the setting to be present and non-empty --
    reject every tenant-table query in that mode. There is no "admin bypass"
    value; the only way to see another org's rows is not to ask the database
    to be tenant-scoped at all, and no application code path does that for a
    tenant table.
    """
    async with SessionLocal() as session, session.begin():
        if org_id is not None:
            await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": str(org_id)})
        yield session


class UnsafeDatabaseRoleError(RuntimeError):
    pass


async def assert_role_cannot_bypass_rls() -> None:
    """
    Refuses to start the app if its own database role is a superuser or has
    BYPASSRLS: either one silently switches off every tenant-isolation policy.
    This is not hypothetical -- the default owner role on managed Postgres
    (Neon's neondb_owner, for one) has BYPASSRLS, so pointing DATABASE_URL at
    the owner instead of tenant_vault_app would pass every request and leak
    every row across organisations.
    """
    async with SessionLocal() as session:
        row = (await session.execute(text("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"))).one()
    if row.rolsuper or row.rolbypassrls:
        raise UnsafeDatabaseRoleError(
            f"DATABASE_URL connects as '{row.current_user}', which can bypass row-level security. "
            "Connect as tenant_vault_app instead."
        )
