import sentry_sdk
from fastapi import FastAPI, Request

from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import time
from app.api.main import api_router
from app.core.config import settings
from app.core.redis import init_redis, close_redis
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
