from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import session as db_session
from app.settings import settings


async def test_app_role_passes_the_guard():
    await db_session.assert_role_cannot_bypass_rls()


async def test_guard_refuses_a_role_that_bypasses_rls(monkeypatch):
    # The admin/owner role in local and CI Postgres is a superuser -- exactly the
    # kind of role the app must never run as.
    admin_engine = create_async_engine(settings.admin_database_url, poolclass=NullPool)
    monkeypatch.setattr(db_session, "SessionLocal", async_sessionmaker(admin_engine, expire_on_commit=False))

    with pytest.raises(db_session.UnsafeDatabaseRoleError):
        await db_session.assert_role_cannot_bypass_rls()
    await admin_engine.dispose()
