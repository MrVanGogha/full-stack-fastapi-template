import secrets
from urllib.parse import quote_plus
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.core.redis import get_redis

STATE_TTL_SECONDS = 300

async def generate_state() -> str:
    state = secrets.token_urlsafe(16)
    redis = await get_redis()
    await redis.set(f"wxstate:{state}", "1", ex=STATE_TTL_SECONDS)
    return state

async def validate_state(state: str) -> bool:
    redis = await get_redis()
    key = f"wxstate:{state}"
    val = await redis.get(key)
    if not val:
        return False
    # single-use state
    try:
        await redis.delete(key)
    except Exception:
        pass
    return True

def build_qrconnect_url(state: str) -> str:
    if not settings.WECHAT_APP_ID or not settings.WECHAT_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="WeChat OAuth not configured")
    base = "https://open.weixin.qq.com/connect/qrconnect"
    params = (
        f"appid={settings.WECHAT_APP_ID}"
        f"&redirect_uri={quote_plus(str(settings.WECHAT_REDIRECT_URI))}"
        f"&response_type=code"
        f"&scope={settings.WECHAT_SCOPE}"
        f"&state={state}#wechat_redirect"
    )
    return f"{base}?{params}"

async def exchange_code_for_openid(code: str) -> dict[str, Any]:
    if not settings.WECHAT_APP_ID or not settings.WECHAT_APP_SECRET:
        raise HTTPException(status_code=500, detail="WeChat OAuth not configured")
    url = "https://api.weixin.qq.com/sns/oauth2/access_token"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params={
            "appid": settings.WECHAT_APP_ID,
            "secret": settings.WECHAT_APP_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        })
        data = resp.json()
        # WeChat returns errcode/errmsg on errors
        if "errcode" in data:
            raise HTTPException(status_code=400, detail=f"WeChat error: {data.get('errmsg')}")
        # Expected keys: access_token, openid, expires_in, refresh_token, scope, unionid(optional)
        openid = data.get("openid")
        if not openid:
            raise HTTPException(status_code=400, detail="Missing openid from WeChat")
        return data