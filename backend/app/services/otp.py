from __future__ import annotations

import secrets
import string
from typing import Optional

from app.core.redis import get_redis


def _otp_key(phone_number: str) -> str:
    return f"otp:{phone_number}"


def _rate_key(phone_number: str) -> str:
    return f"otp:rate:{phone_number}"


def generate_code(length: int = 6) -> str:
    alphabet = string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def issue_code(
    phone_number: str,
    *,
    length: int,
    ttl_seconds: int,
    rate_limit_seconds: int,
) -> str:
    """生成并存储验证码，同时应用简单的发送速率限制。
    返回生成的验证码（供本地环境调试使用）。
    """
    redis = await get_redis()

    # 速率限制：若在限制时间内重复请求则拒绝
    if await redis.get(_rate_key(phone_number)):
        raise RuntimeError("Rate limited")

    code = generate_code(length)
    # 存储验证码
    await redis.set(_otp_key(phone_number), code, ex=ttl_seconds)
    # 设置速率限制标记
    await redis.set(_rate_key(phone_number), "1", ex=rate_limit_seconds)
    return code


async def verify_code(phone_number: str, code: str) -> bool:
    """校验验证码，成功即一次性消费并删除。"""
    redis = await get_redis()
    stored = await redis.get(_otp_key(phone_number))
    if not stored:
        return False
    if secrets.compare_digest(stored, code):
        try:
            await redis.delete(_otp_key(phone_number))
        finally:
            return True
    return False