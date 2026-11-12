"""Redis 与 DB 的对账清理：删除上游 Key 相关命名空间中的孤儿数据。

对账范围：
- KEY:POOL:{masked}  per-key 哈希
- KEY:POOL:WIN:{masked}  近期成败观测窗口
- stats:{prefix}:{model_type}  统计哈希（stats:reqlevel:* 请求级命名空间整体保留）

以 UpstreamKey 表（active + disabled）全量 key 的脱敏前缀为有效集合，
仅清理 DB 中已彻底不存在的 Key 的孤儿数据。
使用 SCAN（非阻塞）遍历，避免 KEYS 阻塞 Redis。
"""
import logging
from typing import Callable, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import UpstreamKey
from service.redis_key_pool import (
    get_key_pool_manager,
    KEY_POOL_PREFIX,
    KEY_WINDOW_PREFIX,
    KEY_FAIL_REASONS,
)
from service.key_stats import APIKeyStats

logger = logging.getLogger(__name__)

# 聚合 key（非 per-key），对账时跳过，避免误删
_AGGREGATE_KEYS = {KEY_FAIL_REASONS}


def _sweep(
    redis,
    pattern: str,
    valid_prefixes: Set[str],
    extract: Callable[[str], str],
    skip: Optional[Set[str]] = None,
) -> int:
    """SCAN 遍历 pattern，对提取出的前缀不在 valid_prefixes 中的 key 执行 delete。

    Args:
        redis: Redis 客户端（decode_responses=True）
        pattern: SCAN 匹配模式
        valid_prefixes: DB 中有效的脱敏前缀集合
        extract: 从完整 key 名中提取脱敏前缀的函数；返回 None 表示保留
        skip: 需要跳过（不判定、不删除）的完整 key 名集合

    Returns:
        删除的 key 数量
    """
    deleted = 0
    cursor = 0
    while True:
        cursor, keys = redis.scan(cursor=cursor, match=pattern, count=100)
        for key in keys:
            if skip and key in skip:
                continue
            prefix = extract(key)
            if prefix is None:
                continue
            if prefix not in valid_prefixes:
                redis.delete(key)
                deleted += 1
                logger.info(f"对账删除孤儿: {key}")
        if cursor == 0:
            break
    return deleted


async def reconcile_upstream_keys_with_db(db: AsyncSession) -> dict:
    """扫描 Redis 上游 Key 命名空间，删除 DB 中已不存在的 Key 的孤儿数据。

    以 UpstreamKey 全表（active + disabled）的脱敏前缀为有效集合：
    - disabled 的 Key 保留统计（看板显示 disabled 状态）
    - 仅清理 DB 中彻底不存在的 Key 的 KEY:POOL:{masked} 与 stats:{prefix}:*

    Args:
        db: 异步数据库会话

    Returns:
        {"pool_deleted": n, "stats_deleted": m, "valid_prefixes": k}
    """
    result = await db.execute(select(UpstreamKey))
    db_keys = result.scalars().all()
    valid_prefixes: Set[str] = {
        APIKeyStats._compute_key_prefix(k.key) for k in db_keys
    }

    redis = get_key_pool_manager().redis

    # 1. 扫描 KEY:POOL:{masked} 与 KEY:POOL:WIN:{masked}，跳过聚合 key
    def _extract_pool(k: str) -> str:
        rest = k[len(KEY_POOL_PREFIX):]
        if rest.startswith("WIN:"):
            return rest[len("WIN:"):]
        return rest

    pool_deleted = _sweep(
        redis,
        f"{KEY_POOL_PREFIX}*",
        valid_prefixes,
        extract=_extract_pool,
        skip=_AGGREGATE_KEYS,
    )

    # 2. 扫描 stats:{prefix}:{model_type}（reqlevel 请求级命名空间整体保留）
    def _extract_stats(k: str) -> Optional[str]:
        prefix = k[len("stats:"):].rpartition(":")[0]
        return None if prefix == "reqlevel" else prefix

    stats_deleted = _sweep(
        redis,
        "stats:*",
        valid_prefixes,
        extract=_extract_stats,
    )

    logger.info(
        f"对账完成：有效前缀 {len(valid_prefixes)} 个，"
        f"删除 pool 孤儿 {pool_deleted} 个，stats 孤儿 {stats_deleted} 个"
    )
    return {
        "pool_deleted": pool_deleted,
        "stats_deleted": stats_deleted,
        "valid_prefixes": len(valid_prefixes),
    }
