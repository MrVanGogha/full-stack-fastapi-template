from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from sqlmodel import Session

from app.core import security
from app.core.db import engine
from app.core.config import settings
from app.models import User
from app.services.jti import is_jti_revoked


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, skip_paths: list[str] | None = None, leeway: float = 0.0):
        super().__init__(app)
        self.skip_paths = tuple(skip_paths or [])
        self.leeway = leeway

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        # Allow CORS preflight
        if method == "OPTIONS":
            return await call_next(request)

        # Built-in public paths (exact and prefix)
        builtin_skip_exact = {
            f"{settings.API_V1_STR}/auth/access-token",
            f"{settings.API_V1_STR}/auth/reset-password/",
            f"{settings.API_V1_STR}/utils/health-check/",
            f"{settings.API_V1_STR}/auth/refresh",
            f"{settings.API_V1_STR}/users/signup",
            f"{settings.API_V1_STR}/auth/phone/send-code",
            f"{settings.API_V1_STR}/auth/phone/login",
            f"{settings.API_V1_STR}/auth/wechat/authorize",
            f"{settings.API_V1_STR}/auth/wechat/callback",
        }
        builtin_skip_prefixes = [
            f"{settings.API_V1_STR}/auth/password-recovery/",
            f"{settings.API_V1_STR}/auth/password-recovery-html-content/",
        ]
        if settings.ENVIRONMENT == "local":
            builtin_skip_prefixes.append(f"{settings.API_V1_STR}/private/")

        if (
            path in builtin_skip_exact
            or any(path.startswith(p) for p in builtin_skip_prefixes)
            or path.startswith("/docs")
            or path.startswith("/redoc")
            or path.endswith("/openapi.json")
            or any(path.startswith(p) for p in self.skip_paths)
        ):
            return await call_next(request)

        # Extract bearer token from Authorization header, query, or cookie
        auth = request.headers.get("Authorization")
        token = None
        if auth and auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        if not token:
            token = request.query_params.get("access_token")
        if not token:
            token = request.cookies.get("access_token")

        if not token:
            return JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "Not authenticated"},
            )

        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[security.ALGORITHM],
                leeway=self.leeway,
            )
            # jti validation: require token id present
            jti = payload.get("jti")
            if not jti:
                return JSONResponse(status_code=401, content={"detail": "Invalid token id"})
            # check revocation blacklist
            try:
                if await is_jti_revoked(jti):
                    return JSONResponse(status_code=401, content={"detail": "Token revoked"})
            except Exception:
                if settings.ENVIRONMENT != "local":
                    return JSONResponse(status_code=503, content={"detail": "Auth service temporarily unavailable"})
                # local environment: skip revocation check on Redis errors

            sub = payload.get("sub")
            if not sub:
                return JSONResponse(status_code=401, content={"detail": "Invalid token subject"})

            with Session(engine) as session:
                user = session.get(User, sub)
                if not user:
                    return JSONResponse(status_code=404, content={"detail": "User not found"})
                if not user.is_active:
                    return JSONResponse(status_code=400, content={"detail": "Inactive user"})
                request.state.user = user
                request.state.token_payload = payload
                request.state.jti = jti
                request.state.exp = payload.get("exp")

        except ExpiredSignatureError:
            return JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer error='invalid_token', error_description='The access token expired'"},
                content={"detail": "Token expired"},
            )
        except InvalidTokenError:
            return JSONResponse(
                status_code=403,
                headers={"WWW-Authenticate": "Bearer error='invalid_token'"},
                content={"detail": "Could not validate credentials"},
            )

        return await call_next(request)