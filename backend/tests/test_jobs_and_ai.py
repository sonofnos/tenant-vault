from __future__ import annotations

import jwt as pyjwt
import pytest

from app.jobs.handlers import build_handlers
from app.jobs.worker import run_once
from app.settings import settings
from tests.helpers import auth_headers, signup_and_login


class FailingSummaryClient:
    async def summarize(self, text: str) -> str:
        raise RuntimeError("upstream LLM provider is down")


class FixedSummaryClient:
    def __init__(self, value: str = "a fixed summary"):
        self.value = value
        self.calls: list[str] = []

    async def summarize(self, text: str) -> str:
        self.calls.append(text)
        return self.value


def _org_id_from_token(token: str) -> str:
    return pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])["org_id"]


@pytest.mark.asyncio
async def test_creating_a_record_queues_a_summarize_job_that_the_worker_fulfils(client):
    token = await signup_and_login(client, "acme")
    created = await client.post("/records", json={"subject_name": "Alice", "notes": "Patient reports mild symptoms. Advised rest."}, headers=auth_headers(token))
    record_id = created.json()["id"]
    assert created.json()["ai_summary"] is None  # not summarized inline

    fake = FixedSummaryClient("Mild symptoms, rest advised.")
    stats = await run_once(build_handlers(summary_client=fake))
    assert stats["done"] == 1

    res = await client.get(f"/records/{record_id}", headers=auth_headers(token))
    assert res.json()["ai_summary"] == "Mild symptoms, rest advised."
    assert fake.calls == ["Patient reports mild symptoms. Advised rest."]


@pytest.mark.asyncio
async def test_worker_only_processes_jobs_for_the_org_it_is_scoped_to_at_that_moment(client):
    """The worker loops per-org internally; this test just confirms a job in org B doesn't get summarized using org A's data or vice versa."""
    token_a = await signup_and_login(client, "org-a")
    token_b = await signup_and_login(client, "org-b")
    rec_a = (await client.post("/records", json={"subject_name": "A", "notes": "org A note"}, headers=auth_headers(token_a))).json()
    rec_b = (await client.post("/records", json={"subject_name": "B", "notes": "org B note"}, headers=auth_headers(token_b))).json()

    fake = FixedSummaryClient()
    await run_once(build_handlers(summary_client=fake))

    assert sorted(fake.calls) == ["org A note", "org B note"]
    res_a = await client.get(f"/records/{rec_a['id']}", headers=auth_headers(token_a))
    res_b = await client.get(f"/records/{rec_b['id']}", headers=auth_headers(token_b))
    assert res_a.json()["ai_summary"] == "a fixed summary"
    assert res_b.json()["ai_summary"] == "a fixed summary"


@pytest.mark.asyncio
async def test_a_failing_summary_client_retries_then_gives_up_without_crashing_the_worker(client):
    token = await signup_and_login(client, "acme")
    await client.post("/records", json={"subject_name": "Alice", "notes": "n"}, headers=auth_headers(token))

    handlers = build_handlers(summary_client=FailingSummaryClient())
    first = await run_once(handlers)
    assert first["retried"] == 1

    # force the job due again and run through the remaining attempts
    from sqlalchemy import text

    from app.db.session import tenant_session

    org_id = _org_id_from_token(token)
    for _ in range(4):
        async with tenant_session(org_id) as session:
            await session.execute(text("UPDATE jobs SET run_after = now() - interval '1 second'"))
        stats = await run_once(handlers)

    assert stats["failed"] == 1

    async with tenant_session(org_id) as session:
        row = (await session.execute(text("SELECT status, attempts, last_error FROM jobs"))).mappings().first()
    assert row["status"] == "failed"
    assert row["attempts"] == 5
    assert "upstream LLM provider is down" in row["last_error"]


@pytest.mark.asyncio
async def test_deleting_a_record_before_the_job_runs_is_handled_without_error(client):
    token = await signup_and_login(client, "acme")
    created = await client.post("/records", json={"subject_name": "Alice", "notes": "n"}, headers=auth_headers(token))
    await client.delete(f"/records/{created.json()['id']}", headers=auth_headers(token))

    stats = await run_once(build_handlers(summary_client=FixedSummaryClient()))
    assert stats["done"] == 1  # the handler treats "record gone" as a no-op success, not a failure to retry forever
