from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def enqueue(session: AsyncSession, org_id: UUID, job_type: str, payload: dict[str, Any]) -> None:
    """
    Enqueues inside the caller's existing transaction (the same one that
    inserted the record or webhook event the job is about), so a rollback of
    that transaction takes the job with it -- there is no way to end up with
    a queued job for a record that was never actually created.
    """
    import json

    await session.execute(
        text("INSERT INTO jobs (org_id, job_type, payload) VALUES (:org_id, :job_type, :payload)"),
        {"org_id": org_id, "job_type": job_type, "payload": json.dumps(payload)},
    )
