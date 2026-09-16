from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateRecordRequest(BaseModel):
    subject_name: str = Field(min_length=1, max_length=200)
    notes: str = Field(min_length=1, max_length=10_000)


class UpdateRecordStatusRequest(BaseModel):
    status: str = Field(pattern="^(open|reviewed|closed)$")


class RecordView(BaseModel):
    id: UUID
    subject_name: str
    notes: str
    status: str
    ai_summary: str | None
    created_at: datetime
    updated_at: datetime
