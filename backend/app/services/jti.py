from __future__ import annotations

import time
from typing import Optional

from app.core.redis import get_redis


def jti_key(jti: str) -> str:
    """生成指定 JTI 的 Redis 键，格式为 'jti:{jti}'。
    参数:
        jti: 令牌的唯一标识（JWT ID）。
    返回:
        Redis 键字符串。
    """
    return f"jti:{jti}"


async def is_jti_revoked(jti: str) -> bool:
    """检查某个 JTI 是否已被撤销。
    通过查询 Redis 中该键是否存在来判断，存在即表示已撤销。
    参数:
        jti: 令牌的唯一标识（JWT ID）。
    返回:
        True 表示已撤销；False 表示未撤销。
    """
    redis = await get_redis()
    val = await redis.get(jti_key(jti))
    return val is not None


async def revoke_jti(jti: str, exp_ts: Optional[float] = None) -> bool:
    """
    将给定 JTI 标记为撤销，并可选地设置 TTL 为令牌剩余有效期。
    参数:
        jti: 令牌的唯一标识（JWT ID）。
        exp_ts: 令牌过期时间的 Unix 时间戳（秒）。如果提供，则按剩余有效期设置 TTL。
    返回:
        True 表示设置成功；如果剩余有效期小于等于 0 则返回 False。
    """
    redis = await get_redis()
    ttl: Optional[int] = None
    if exp_ts is not None:
        now = time.time()
        remaining = int(exp_ts - now)
        if remaining <= 0:
            return False
        ttl = remaining
    # store a simple marker value
    if ttl is not None:
        await redis.set(jti_key(jti), "revoked", ex=ttl)
    else:
        await redis.set(jti_key(jti), "revoked")
    return True


async def token_status(jti: str) -> str:
    """返回令牌状态字符串。
    参数:
        jti: 令牌的唯一标识（JWT ID）。
    返回:
        'revoked' 表示已撤销，'active' 表示未撤销。
    """
    return "revoked" if (await is_jti_revoked(jti)) else "active"