from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def record_audit(
    session: AsyncSession, org_id: UUID, actor_id: UUID, action: str, entity: str, entity_id: UUID | None, metadata: dict[str, Any] | None = None
) -> None:
    """
    Written in the same transaction as the change it describes, via the same
    tenant-scoped session -- not a separate connection, not fire-and-forget.
    If the audit write fails, the transaction it's part of rolls back along
    with it, so there is no way for a mutation to succeed silently unaudited.
    """
    import json

    await session.execute(
        text("INSERT INTO audit_log (org_id, actor_id, action, entity, entity_id, metadata) VALUES (:org_id, :actor_id, :action, :entity, :entity_id, :metadata)"),
        {"org_id": org_id, "actor_id": actor_id, "action": action, "entity": entity, "entity_id": entity_id, "metadata": json.dumps(metadata or {})},
    )
