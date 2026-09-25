from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth.routes import router as auth_router
from .db.session import assert_role_cannot_bypass_rls
from .jobs.handlers import build_handlers
from .jobs.worker import run_forever
from .records.routes import router as records_router
from .settings import settings
from .webhooks.routes import router as webhooks_router


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await assert_role_cannot_bypass_rls()
    worker = asyncio.create_task(run_forever(build_handlers())) if settings.run_worker_in_process else None
    try:
        yield
    finally:
        if worker is not None:
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker


app = FastAPI(title="tenant-vault", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(records_router)
app.include_router(webhooks_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "tenant-vault"}
