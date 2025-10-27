from datetime import datetime, timezone, timedelta
import time
import secrets

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from jwt.exceptions import InvalidTokenError
from fastapi.responses import RedirectResponse

from app import crud
from app.api.deps import CurrentUser, TokenDep, get_current_active_superuser, SessionDep
from app.core import security
from app.core.config import settings
from app.models import Message, Token, PhoneNumberRequest, PhoneLoginRequest, UserCreate
from app.services.jti import revoke_jti, is_jti_revoked
from app.services.otp import issue_code, verify_code
from app.services.wechat_oauth import generate_state, build_qrconnect_url, validate_state, exchange_code_for_openid
from app.services.sms import send_login_code as send_sms_login_code

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/revoke/me", response_model=Message)
async def revoke_current_token(token: TokenDep, current_user: CurrentUser) -> Message:
    """Revoke the caller's current access token until it expires."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not exp:
            raise HTTPException(status_code=400, detail="Invalid token")
        await revoke_jti(jti, exp_ts=float(exp))
        return Message(message="Token revoked")
    except InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")


@router.post(
    "/revoke/{jti}", dependencies=[Depends(get_current_active_superuser)], response_model=Message
)
async def revoke_by_jti(jti: str, ttl_seconds: int | None = None) -> Message:
    """Revoke a token by its JTI. Superuser only.

    Optionally provide ttl_seconds to auto-expire the revocation entry.
    """
    exp_ts: float | None = None
    if ttl_seconds and ttl_seconds > 0:
        exp_ts = time.time() + ttl_seconds
    await revoke_jti(jti, exp_ts=exp_ts)
    return Message(message="Token revoked by jti")


@router.get("/status/me")
async def jti_status_me(token: TokenDep, current_user: CurrentUser) -> dict:
    """Check revocation status of the caller's current token."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        jti = payload.get("jti")
        if not jti:
            raise HTTPException(status_code=400, detail="Invalid token")
        revoked = await is_jti_revoked(jti)
        return {"jti": jti, "revoked": revoked}
    except InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")


@router.get(
    "/status/{jti}", dependencies=[Depends(get_current_active_superuser)]
)
async def jti_status(jti: str) -> dict:
    """Check revocation status of a JTI. Superuser only."""
    revoked = await is_jti_revoked(jti)
    return {"jti": jti, "revoked": revoked}


@router.post("/refresh", response_model=Token)
async def refresh_token(request: Request, response: Response) -> Token:
    """使用刷新令牌获取新的访问令牌，并旋转刷新令牌。"""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        payload = jwt.decode(
            refresh_token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        if payload.get("token_use") != "refresh":
            raise HTTPException(status_code=400, detail="Invalid token type")
        jti = payload.get("jti")
        exp = payload.get("exp")
        sub = payload.get("sub")
        if not jti or not exp or not sub:
            raise HTTPException(status_code=400, detail="Invalid token")
        if await is_jti_revoked(jti):
            raise HTTPException(status_code=401, detail="Token revoked")

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        new_access_token = security.create_access_token(
            sub, expires_delta=access_token_expires
        )

        # 旋转刷新令牌：撤销旧的并签发新的
        await revoke_jti(jti, exp_ts=float(exp))
        refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        new_refresh_token = security.create_refresh_token(
            sub, expires_delta=refresh_token_expires
        )
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=settings.ENVIRONMENT != "local",
            samesite="lax",
            max_age=int(refresh_token_expires.total_seconds()),
            path="/",
        )

        return Token(access_token=new_access_token)
    except InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")


@router.post("/logout", response_model=Message)
async def logout(token: TokenDep, current_user: CurrentUser, response: Response, request: Request) -> Message:
    """Logout current user: revoke current access token and clear cookies."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not exp:
            raise HTTPException(status_code=400, detail="Invalid token")
        await revoke_jti(jti, exp_ts=float(exp))
        # clear access token cookie if present (compat)
        response.delete_cookie("access_token")

        # 同时撤销并清除 refresh cookie（如果存在）
        refresh_token = request.cookies.get("refresh_token")
        if refresh_token:
            try:
                rp = jwt.decode(
                    refresh_token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
                )
                rjti = rp.get("jti")
                rexp = rp.get("exp")
                if rjti and rexp:
                    await revoke_jti(rjti, exp_ts=float(rexp))
            except InvalidTokenError:
                pass
            response.delete_cookie("refresh_token")

        return Message(message="Logged out")
    except InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")


@router.post("/phone/send-code", response_model=Message)
async def send_phone_code(body: PhoneNumberRequest) -> Message:
    """向手机号发送登录验证码。
    为避免用户枚举，始终返回成功信息。
    本地环境可回显验证码以便开发调试。
    """
    # 修改：不论该手机号是否已绑定用户，均生成并发送验证码
    try:
        code = await issue_code(
            body.phone_number,
            length=settings.OTP_CODE_LENGTH,
            ttl_seconds=settings.OTP_CODE_TTL_SECONDS,
            rate_limit_seconds=settings.OTP_RATE_LIMIT_SECONDS,
        )
        # 发送登录短信（根据 settings.SMS_PROVIDER 选择供应商）
        await send_sms_login_code(body.phone_number, code)
        # 删除多余的打印，保留日志与返回
        if settings.ENVIRONMENT == "local" and getattr(settings, "OTP_LOCAL_ECHO", True):
            return Message(message=f"Verification code sent: {code}")
    except RuntimeError:
        raise HTTPException(status_code=429, detail="Too many requests")
    return Message(message="Verification code sent")


@router.post("/phone/login", response_model=Token)
async def phone_login(session: SessionDep, body: PhoneLoginRequest, response: Response, request: Request) -> Token:
    """使用手机号+验证码登录，签发访问令牌并设置刷新 Cookie。"""
    valid = await verify_code(body.phone_number, body.code)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    user = crud.get_user_by_phone(session=session, phone_number=body.phone_number)
    if not user:
        # 修改：未绑定用户时，自动创建一个新用户并绑定此手机号
        # 生成一个占位邮箱与随机密码，用户后续可在设置中修改邮箱/密码
        digits = "".join(ch for ch in body.phone_number if ch.isdigit())
        placeholder_email = f"p{digits}@example.com" if digits else f"phone_{int(time.time())}@example.com"
        random_password = secrets.token_hex(16)
        try:
            user = crud.create_user(
                session=session,
                user_create=UserCreate(
                    email=placeholder_email,
                    password=random_password,
                    full_name=None,
                    phone_number=body.phone_number,
                ),
            )
        except Exception as e:
            # 如果占位邮箱冲突或其他错误
            raise HTTPException(status_code=500, detail="Failed to create user for phone login")

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    # 记录最后一次登录时间和 IP
    try:
        from datetime import datetime
        user.last_login_time = datetime.utcnow()
        # 获取客户端 IP：优先 X-Forwarded-For，其次 request.client.host
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            user.last_login_ip = xff.split(",")[0].strip()
        else:
            user.last_login_ip = request.client.host if request.client else None
        session.add(user)
        session.commit()
    except Exception:
        session.rollback()

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    access_token = security.create_access_token(user.id, expires_delta=access_token_expires)
    refresh_token = security.create_refresh_token(user.id, expires_delta=refresh_token_expires)

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT != "local",
        samesite="lax",
        max_age=int(refresh_token_expires.total_seconds()),
        path="/",
    )
    return Token(access_token=access_token)

@router.get("/wechat/authorize")
async def wechat_authorize() -> RedirectResponse:
    """Generate state, construct WeChat QR connect URL, and redirect the browser."""
    state = await generate_state()
    url = build_qrconnect_url(state)
    return RedirectResponse(url)

@router.get("/wechat/login")
async def wechat_callback(request: Request, response: Response, session: SessionDep, code: str, state: str) -> RedirectResponse:
    """Handle WeChat callback: validate state, exchange code for openid, login or create user, set refresh cookie, and redirect frontend."""
    ok = await validate_state(state)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid state")
    data = await exchange_code_for_openid(code)
    openid = data.get("openid")
    if not openid:
        raise HTTPException(status_code=400, detail="Missing openid")
    user = crud.get_user_by_wechat_openid(session=session, openid=openid)
    if not user:
        placeholder_email = f"wx_{openid}@example.com"
        random_password = secrets.token_hex(16)
        try:
            user = crud.create_user(
                session=session,
                user_create=UserCreate(
                    email=placeholder_email,
                    password=random_password,
                ),
            )
            from app.models import UserUpdate
            crud.update_user(session=session, db_user=user, user_in=UserUpdate())
            user.wechat_openid = openid
            session.add(user)
            session.commit()
        except Exception:
            session.rollback()
            raise HTTPException(status_code=500, detail="Failed to create user for WeChat login")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    try:
        from datetime import datetime
        user.last_login_time = datetime.utcnow()
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            user.last_login_ip = xff.split(",")[0].strip()
        else:
            user.last_login_ip = request.client.host if request.client else None
        session.add(user)
        session.commit()
    except Exception:
        session.rollback()
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    access_token = security.create_access_token(user.id, expires_delta=access_token_expires)
    refresh_token = security.create_refresh_token(user.id, expires_delta=refresh_token_expires)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT != "local",
        samesite="lax",
        max_age=int(refresh_token_expires.total_seconds()),
        path="/",
    )
    frontend_url = f"{settings.FRONTEND_HOST}/login-success?access_token={access_token}"
    return RedirectResponse(frontend_url)