from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from ..audit import record_audit
from ..auth.dependencies import current_user, require_role
from ..auth.security import AuthenticatedUser
from ..db.session import tenant_session
from ..jobs.queue import enqueue
from .schemas import CreateRecordRequest, RecordView, UpdateRecordStatusRequest

router = APIRouter(prefix="/records", tags=["records"])


@router.post("", response_model=RecordView, status_code=201)
async def create_record(body: CreateRecordRequest, user: AuthenticatedUser = Depends(require_role("member"))) -> RecordView:  # noqa: B008
    async with tenant_session(user.org_id) as session:
        result = await session.execute(
            text(
                "INSERT INTO records (org_id, created_by, subject_name, notes) VALUES (:org_id, :created_by, :subject_name, :notes) "
                "RETURNING id, subject_name, notes, status, ai_summary, created_at, updated_at"
            ),
            {"org_id": user.org_id, "created_by": user.user_id, "subject_name": body.subject_name, "notes": body.notes},
        )
        row = result.mappings().one()
        await record_audit(session, user.org_id, user.user_id, "record.created", "record", row["id"])
        # Queued, not run inline: summarizing shouldn't make record creation
        # wait on an LLM call. See app/jobs/worker.py and app/ai/summarize.py.
        await enqueue(session, user.org_id, "summarize_record", {"record_id": str(row["id"])})
    return RecordView(**row)


@router.get("", response_model=list[RecordView])
async def list_records(user: AuthenticatedUser = Depends(current_user)) -> list[RecordView]:
    async with tenant_session(user.org_id) as session:
        result = await session.execute(
            text("SELECT id, subject_name, notes, status, ai_summary, created_at, updated_at FROM records ORDER BY created_at DESC")
        )
        return [RecordView(**row) for row in result.mappings().all()]


@router.get("/{record_id}", response_model=RecordView)
async def get_record(record_id: UUID, user: AuthenticatedUser = Depends(current_user)) -> RecordView:
    async with tenant_session(user.org_id) as session:
        result = await session.execute(
            text("SELECT id, subject_name, notes, status, ai_summary, created_at, updated_at FROM records WHERE id = :id"),
            {"id": record_id},
        )
        row = result.mappings().first()
    # A record from another org is not "forbidden" -- RLS means the row
    # was never in the result set to begin with, so this is correctly a 404,
    # not a 403. A 403 would confirm the record exists somewhere; a 404 does not.
    if row is None:
        raise HTTPException(status_code=404, detail="record not found")
    return RecordView(**row)


@router.patch("/{record_id}/status", response_model=RecordView)
async def update_status(record_id: UUID, body: UpdateRecordStatusRequest, user: AuthenticatedUser = Depends(require_role("member"))) -> RecordView:  # noqa: B008
    async with tenant_session(user.org_id) as session:
        result = await session.execute(
            text("UPDATE records SET status = :status, updated_at = now() WHERE id = :id RETURNING id, subject_name, notes, status, ai_summary, created_at, updated_at"),
            {"status": body.status, "id": record_id},
        )
        row = result.mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="record not found")
        await record_audit(session, user.org_id, user.user_id, "record.status_changed", "record", record_id, {"status": body.status})
    return RecordView(**row)


@router.delete("/{record_id}", status_code=204)
async def delete_record(record_id: UUID, user: AuthenticatedUser = Depends(require_role("admin"))) -> None:  # noqa: B008
    async with tenant_session(user.org_id) as session:
        result = await session.execute(text("DELETE FROM records WHERE id = :id RETURNING id"), {"id": record_id})
        if result.first() is None:
            raise HTTPException(status_code=404, detail="record not found")
        await record_audit(session, user.org_id, user.user_id, "record.deleted", "record", record_id)
