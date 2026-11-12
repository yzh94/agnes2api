"""系统配置初始化与 Redis 同步（供 main.py 启动时及 management.py 按需调用）。"""
import logging
from sqlalchemy import select

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_CONFIGS = [
    ("rate_limit_enabled", "1"),
    ("rate_limit_uploader_rpm", "60"),
    ("rate_limit_non_uploader_rpm", "10"),
]


def _sync_configs_to_redis(configs) -> None:
    """将 SystemConfig 列表写入 Redis sys:* 键（供 rate_limit.py 读取）。"""
    try:
        from service.redis_key_pool import get_key_pool_manager
        redis = get_key_pool_manager().redis
        for cfg in configs:
            redis.set(f"sys:{cfg.key}", cfg.value)
    except Exception as e:
        logger.warning(f"同步系统配置到 Redis 失败: {e}")


async def ensure_system_config_initialized(db) -> None:
    """确保 SystemConfig 表有默认值，并同步到 Redis。

    幂等：已存在配置时不覆盖；表为空时才写入默认值。
    供 main.py 启动时及 management.py GET /system-config 复用。
    """
    from models.database import SystemConfig

    result = await db.execute(select(SystemConfig))
    configs = result.scalars().all()

    if not configs:
        for k, v in DEFAULT_SYSTEM_CONFIGS:
            db.add(SystemConfig(key=k, value=v))
        await db.commit()
        configs = (await db.execute(select(SystemConfig))).scalars().all()
        logger.info("已初始化默认系统配置")

    _sync_configs_to_redis(configs)
    logger.info(f"已同步 {len(configs)} 项系统配置到 Redis")
