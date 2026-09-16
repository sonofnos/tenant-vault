from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from app.settings import settings
from tests.helpers import signup_and_login


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(settings.webhook_signing_secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_rejects_bad_signature(client):
    await signup_and_login(client, "acme")
    body = json.dumps({"type": "lab_result"}).encode()
    resp = await client.post("/webhooks/acme/inbound", content=body, headers={"X-Signature": "sha256=wrong", "X-Event-Id": "evt-1"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rejects_unknown_org(client):
    body = json.dumps({"type": "lab_result"}).encode()
    resp = await client.post("/webhooks/does-not-exist/inbound", content=body, headers={"X-Signature": _sign(body), "X-Event-Id": "evt-1"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_accepts_a_valid_signed_event_and_drops_a_replay(client):
    await signup_and_login(client, "acme")
    body = json.dumps({"type": "lab_result", "value": 1}).encode()
    headers = {"X-Signature": _sign(body), "X-Event-Id": "evt-1"}

    first = await client.post("/webhooks/acme/inbound", content=body, headers=headers)
    second = await client.post("/webhooks/acme/inbound", content=body, headers=headers)

    assert first.status_code == 202
    assert first.json()["status"] == "accepted"
    assert second.status_code == 202
    assert second.json()["status"] == "duplicate"
