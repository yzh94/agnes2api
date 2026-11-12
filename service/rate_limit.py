"""用户速率限制（RPM）。

分两档：上传 Key 的用户（uploader）/ 未上传 Key 的用户（non_uploader）。
配置从 Redis sys:* 键读取，带短缓存。超限返回 429。
"""
import logging
import time
from typing import Any, Optional

from config import settings

logger = logging.getLogger(__name__)

# 配置缓存（10s 刷新）
_config_cache: dict[str, str] = {}
_config_cache_ts: float = 0.0
_CONFIG_TTL = 10


def _read_config() -> dict[str, str]:
    """从 Redis sys:* 键读取速率限制配置，带短缓存。"""
    global _config_cache, _config_cache_ts
    now = time.monotonic()
    if now - _config_cache_ts < _CONFIG_TTL:
        return _config_cache

    _config_cache_ts = now
    defaults = {
        "rate_limit_enabled": "1",
        "rate_limit_uploader_rpm": "60",
        "rate_limit_non_uploader_rpm": "10",
    }
    cfg: dict[str, str] = dict(defaults)

    if settings.redis_conn_string:
        try:
            from service.redis_key_pool import get_key_pool_manager
            r = get_key_pool_manager().redis
            keys = ["sys:rate_limit_enabled", "sys:rate_limit_uploader_rpm",
                    "sys:rate_limit_non_uploader_rpm"]
            values = r.mget(keys)
            names = ["rate_limit_enabled", "rate_limit_uploader_rpm",
                     "rate_limit_non_uploader_rpm"]
            for name, val in zip(names, values):
                if val is not None:
                    cfg[name] = val
        except Exception:
            pass  # 使用默认值

    _config_cache = cfg
    return cfg


class RateLimitError(Exception):
    """速率超限异常。"""
    def __init__(self, rpm: int):
        self.rpm = rpm
        super().__init__(f"Rate limit exceeded: {rpm} requests per minute")


async def enforce_rate_limit(user_id: int) -> None:
    """检查并执行速率限制（async）。

    Args:
        user_id: 用户 ID（0 = master key，跳过限速）
    """
    if user_id == 0:
        return

    cfg = _read_config()
    if cfg.get("rate_limit_enabled", "1") != "1":
        return

    try:
        from service.redis_key_pool import get_key_pool_manager
        r = get_key_pool_manager().redis

        if await _check_is_admin(user_id, r):
            return

        # 获取 RPM 档位
        is_uploader = await _check_is_uploader(user_id, r)
        rpm_limit = int(cfg.get("rate_limit_uploader_rpm", "60") if is_uploader
                        else cfg.get("rate_limit_non_uploader_rpm", "10"))

        # 固定窗口计数
        minute_bucket = int(time.time()) // 60
        rate_key = f"rate:{user_id}:{minute_bucket}"
        current = r.incr(rate_key)
        if current == 1:
            r.expire(rate_key, 120)  # 延长 60s 防边界

        if current > rpm_limit:
            raise RateLimitError(rpm_limit)
    except RateLimitError:
        raise
    except Exception as e:
        logger.warning(f"Rate limit check failed: {e}")


async def _check_is_admin(user_id: int, r: Any) -> bool:
    """检查用户是否为 admin（async）。"""
    cache_key = f"user_role:{user_id}"
    cached = r.get(cache_key)
    if cached == "admin":
        return True
    if cached:
        return False

    try:
        from models.database import AsyncSessionLocal, User
        from sqlalchemy import select

        async def _query():
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User.role).where(User.id == user_id).limit(1)
                )
                return result.scalar_one_or_none()

        role = await _query()
    except Exception:
        role = None

    cached_role = role or "unknown"
    r.setex(cache_key, 300, cached_role)
    return role == "admin"


async def _check_is_uploader(user_id: int, r: Any) -> bool:
    """检查用户是否有 active 的上游 Key（async）。"""
    cache_key = f"user_tier:{user_id}"
    cached = r.get(cache_key)
    if cached == "uploader":
        return True
    if cached == "non_uploader":
        return False

    # DB 查询
    try:
        from models.database import AsyncSessionLocal, UpstreamKey
        from sqlalchemy import select

        async def _query():
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(UpstreamKey.id).where(
                        UpstreamKey.user_id == user_id,
                        UpstreamKey.status == "active"
                    ).limit(1)
                )
                return result.scalar_one_or_none() is not None

        has_key = await _query()
    except Exception:
        has_key = False

    tier = "uploader" if has_key else "non_uploader"
    r.setex(cache_key, 300, tier)
    return has_key


def refresh_user_tier(user_id: int) -> None:
    """刷新用户的 uploader 缓存（上传/删除/禁用/启用上游 Key 时调用）。"""
    if not settings.redis_conn_string:
        return
    try:
        from service.redis_key_pool import get_key_pool_manager
        r = get_key_pool_manager().redis
        r.delete(f"user_tier:{user_id}")
        r.delete(f"user_role:{user_id}")
    except Exception:
        pass
