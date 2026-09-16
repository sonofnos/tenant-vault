from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import text

from ..db.session import tenant_session
from ..jobs.queue import enqueue
from ..settings import settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify(payload: bytes, signature_header: str) -> bool:
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.webhook_signing_secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


async def _org_id_for_slug(slug: str):
    async with tenant_session(org_id=None) as session:
        result = await session.execute(text("SELECT id FROM organizations WHERE slug = :slug"), {"slug": slug})
        row = result.first()
    return row[0] if row else None


@router.post("/{org_slug}/inbound", status_code=202)
async def inbound_webhook(
    org_slug: str,
    request: Request,
    x_event_id: str = Header(..., alias="X-Event-Id"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """
    The tenant is identified by the URL path (a per-org webhook endpoint,
    the way Stripe Connect or a per-tenant integration URL works), not by a
    header the sender could get wrong or a token that would need its own
    RBAC story. The signature proves this specific org's external system
    sent it; the path segment says which org's data it's allowed to become.
    """
    org_id = await _org_id_for_slug(org_slug)
    if org_id is None:
        raise HTTPException(status_code=404, detail="unknown organization")

    body = await request.body()
    if not _verify(body, x_signature):
        raise HTTPException(status_code=401, detail="invalid signature")

    import json

    payload = json.loads(body)
    async with tenant_session(org_id) as session:
        existing = await session.execute(text("SELECT 1 FROM webhook_events WHERE event_id = :id"), {"id": x_event_id})
        if existing.first() is not None:
            return {"status": "duplicate"}

        await session.execute(
            text("INSERT INTO webhook_events (event_id, org_id, event_type, payload) VALUES (:id, :org_id, :type, :payload)"),
            {"id": x_event_id, "org_id": org_id, "type": payload.get("type", "unknown"), "payload": json.dumps(payload)},
        )
        await enqueue(session, org_id, "process_webhook", {"event_id": x_event_id})
    return {"status": "accepted"}
