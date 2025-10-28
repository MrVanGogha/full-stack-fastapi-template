import sentry_sdk
from fastapi import FastAPI, Request

from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import time
from app.api.main import api_router
from app.core.config import settings
from app.core.redis import init_redis, close_redis
import asyncio
from datetime import datetime, timedelta
from sqlmodel import Session, select
from app.core.db import engine
from app.models import Item
# Remove inline JSONResponse/jwt/sqlmodel imports; use external middleware module
from app.middleware.auth import AuthMiddleware


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)



app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Register auth middleware
app.add_middleware(
    AuthMiddleware,
    skip_paths=[
        f"{settings.API_V1_STR}/auth/access-token",
        f"{settings.API_V1_STR}/auth/password-recovery",
        f"{settings.API_V1_STR}/auth/password-recovery-html-content",
        f"{settings.API_V1_STR}/auth/reset-password/",
        f"{settings.API_V1_STR}/utils/health-check/",
    ],
    leeway=5.0,
)

app.add_event_handler("startup", init_redis)
app.add_event_handler("shutdown", close_redis)

# --- Trash purge scheduler ---
_purge_task: asyncio.Task | None = None

async def _purge_trash_once() -> None:
    retention_days = getattr(settings, "TRASH_RETENTION_DAYS", 7)
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    with Session(engine) as session:
        items = session.exec(
            select(Item).where(Item.deleted_at != None, Item.deleted_at <= cutoff)  # type: ignore
        ).all()
        if items:
            for it in items:
                session.delete(it)
            session.commit()

async def _purge_trash_loop() -> None:
    try:
        while True:
            # Run once per day at ~03:00 UTC (simple sleep-based scheduler)
            now = datetime.utcnow()
            target = datetime(now.year, now.month, now.day, 3, 0, 0)
            if now >= target:
                target += timedelta(days=1)
            sleep_seconds = (target - now).total_seconds()
            await asyncio.sleep(sleep_seconds)
            await _purge_trash_once()
    except asyncio.CancelledError:
        return

def _start_purge_scheduler() -> None:
    global _purge_task
    if _purge_task is None:
        _purge_task = asyncio.create_task(_purge_trash_loop())

app.add_event_handler("startup", _start_purge_scheduler)

class ProcessTimeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response


# Register class-based middleware
app.add_middleware(ProcessTimeMiddleware)
    
app.include_router(api_router, prefix=settings.API_V1_STR)
