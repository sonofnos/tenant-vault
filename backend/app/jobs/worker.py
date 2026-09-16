from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import tenant_session
from ..settings import settings

logger = logging.getLogger(__name__)

JobHandler = Callable[[AsyncSession, UUID, dict], Awaitable[None]]

MAX_ATTEMPTS = 5


async def _all_org_ids() -> list[UUID]:
    async with tenant_session(org_id=None) as session:
        result = await session.execute(text("SELECT id FROM organizations"))
        return [row[0] for row in result.all()]


async def run_once(handlers: dict[str, JobHandler]) -> dict[str, int]:
    """
    Processes at most one batch of due jobs per organization. There is no
    "process jobs for every org" query, because that query would have to run
    outside RLS to see rows across tenants -- the same shape of problem
    login had. Instead the worker enumerates orgs (organizations carries no
    sensitive data and isn't RLS-protected) and opens one tenant-scoped
    transaction per org, same as any request would.

    `FOR UPDATE SKIP LOCKED` lets multiple worker instances run against the
    same org concurrently without two workers claiming the same job.
    """
    stats = {"done": 0, "failed": 0, "retried": 0}
    for org_id in await _all_org_ids():
        async with tenant_session(org_id) as session:
            result = await session.execute(
                text("SELECT id, job_type, payload, attempts FROM jobs WHERE status = 'pending' AND run_after <= now() ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 10")
            )
            jobs = result.mappings().all()
            for job in jobs:
                handler = handlers.get(job["job_type"])
                if handler is None:
                    await session.execute(text("UPDATE jobs SET status = 'failed', last_error = 'no handler registered' WHERE id = :id"), {"id": job["id"]})
                    stats["failed"] += 1
                    continue
                try:
                    payload = job["payload"] if isinstance(job["payload"], dict) else json.loads(job["payload"])
                    await handler(session, org_id, payload)
                    await session.execute(text("UPDATE jobs SET status = 'done' WHERE id = :id"), {"id": job["id"]})
                    stats["done"] += 1
                except Exception as exc:  # noqa: BLE001
                    attempts = job["attempts"] + 1
                    if attempts >= MAX_ATTEMPTS:
                        await session.execute(
                            text("UPDATE jobs SET status = 'failed', attempts = :a, last_error = :e WHERE id = :id"),
                            {"a": attempts, "e": str(exc), "id": job["id"]},
                        )
                        stats["failed"] += 1
                    else:
                        delay = min(300, 2**attempts)
                        await session.execute(
                            text("UPDATE jobs SET attempts = :a, last_error = :e, run_after = now() + (:delay || ' seconds')::interval WHERE id = :id"),
                            {"a": attempts, "e": str(exc), "delay": str(delay), "id": job["id"]},
                        )
                        stats["retried"] += 1
    return stats


async def run_forever(handlers: dict[str, JobHandler]) -> None:  # pragma: no cover - exercised via run_once in tests
    while True:
        try:
            await run_once(handlers)
        except Exception:
            logger.exception("job worker tick failed")
        await asyncio.sleep(settings.job_poll_interval_seconds)
