from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..ai.summarize import SummaryClient, TemplateSummaryClient, summarize_record


def build_handlers(summary_client: SummaryClient | None = None) -> dict:
    """
    A factory rather than a module-level dict, so tests can inject a fake
    SummaryClient (or a fake webhook processor) without monkeypatching a
    global. Production code calls build_handlers() with no arguments and
    gets the real default.
    """
    client = summary_client or TemplateSummaryClient()

    async def handle_summarize(session: AsyncSession, org_id: UUID, payload: dict) -> None:
        await summarize_record(session, org_id, UUID(payload["record_id"]), client)

    async def handle_webhook(session: AsyncSession, org_id: UUID, payload: dict) -> None:
        # A real integration would branch on the webhook's event_type here
        # (e.g. update a record from an external lab-results system). Left
        # as a no-op that just proves the job ran, since the point being
        # demonstrated is the queue and the tenant scoping, not a specific
        # third-party payload shape.
        return

    return {
        "summarize_record": handle_summarize,
        "process_webhook": handle_webhook,
    }
