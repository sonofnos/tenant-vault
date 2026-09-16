from __future__ import annotations

from fastapi import FastAPI

from .auth.routes import router as auth_router
from .records.routes import router as records_router
from .webhooks.routes import router as webhooks_router

app = FastAPI(title="tenant-vault")
app.include_router(auth_router)
app.include_router(records_router)
app.include_router(webhooks_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "tenant-vault"}
