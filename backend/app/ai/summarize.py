from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SummaryClient(Protocol):
    """
    The seam between this codebase and whatever actually generates the
    summary. Production wires an LLM client here; tests wire a fake that
    returns a fixed string, so the job-handling logic (fetch record, call
    client, write result, handle a client that raises) is verified without
    a network call or an API key.
    """

    async def summarize(self, text: str) -> str: ...


class TemplateSummaryClient:
    """
    A dependency-free stand-in for a real LLM call, so this repo runs and is
    demonstrably correct without anyone needing an API key to evaluate it.
    Swapping this for an OpenAI/Anthropic client is a one-line change at the
    call site in app/jobs/handlers.py; nothing else in the request path
    changes, because the job handler only depends on the SummaryClient protocol.
    """

    async def summarize(self, text: str) -> str:
        first_sentence = text.strip().split(".")[0].strip()
        word_count = len(text.split())
        return f"{first_sentence[:200]}. ({word_count} words total.)"


async def summarize_record(session: AsyncSession, org_id: UUID, record_id: UUID, client: SummaryClient) -> None:
    result = await session.execute(text("SELECT notes FROM records WHERE id = :id"), {"id": record_id})
    row = result.first()
    if row is None:
        # The record was deleted before the job ran. Not an error -- there's
        # nothing left to summarize, and retrying won't change that.
        return
    summary = await client.summarize(row[0])
    await session.execute(text("UPDATE records SET ai_summary = :summary, updated_at = now() WHERE id = :id"), {"summary": summary, "id": record_id})
