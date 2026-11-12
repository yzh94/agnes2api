"""上游 Key 自动禁用模块。

当上游返回 401 或错误消息包含"该令牌状态不可用"时，
自动将对应的 UpstreamKey 在数据库中永久禁用并重建 Key Pool。
新增：禁用后检查用户速率降级。
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def disable_key_and_check_user_rate(
    db,
    up_key,
    reason: str,
) -> None:
    """禁用 Key 并检查用户速率降级。

    禁用后检查该用户是否还有其他 active Key：
    - 无 → 清除 Redis 中的 uploader 缓存，用户降级为 non_uploader 速率
    - 有 → 保持不变

    Args:
        db: SQLAlchemy async session
        up_key: UpstreamKey ORM 对象
        reason: 禁用原因
    """
    # 1. 标记禁用
    up_key.status = "disabled"
    up_key.disabled_reason = reason
    up_key.disabled_at = datetime.now(timezone.utc)
    await db.commit()

    logger.warning(f"Key '{up_key.name}' 已禁用: {reason}")

    # 3. 检查用户是否还有 active Key
    if up_key.user_id:
        from models.database import UpstreamKey as UK
        from sqlalchemy import select

        result = await db.execute(
            select(UK.id).where(
                UK.user_id == up_key.user_id,
                UK.status == "active"
            ).limit(1)
        )
        has_active = result.scalar_one_or_none() is not None

        if not has_active:
            # 用户无 active Key，降级为非上传用户速率
            from service.rate_limit import refresh_user_tier
            refresh_user_tier(up_key.user_id)
            logger.info(f"用户 {up_key.user_id} 已无 active Key，速率已降级")

    logger.info("Key 禁用完成")


async def check_and_disable_key_on_401(
    full_key: str,
    status_code: int,
    err_body: dict,
) -> bool:
    """检测上游错误是否满足自动禁用条件，若满足则永久禁用该 Key。

    触发条件（满足任一）：
        - HTTP 状态码 == 401
        - 错误消息包含 "该令牌状态不可用"

    Args:
        full_key: 完整的 API Key
        status_code: 上游返回的 HTTP 状态码
        err_body: 上游返回的错误响应体（dict）

    Returns:
        bool: 是否执行了禁用操作
    """
    # 提取错误消息
    error_msg = ""
    if isinstance(err_body, dict):
        error = err_body.get("error", {})
        if isinstance(error, dict):
            error_msg = error.get("message", "")
        elif isinstance(error, str):
            error_msg = error
    if not error_msg and isinstance(err_body, dict):
        error_msg = err_body.get("message", "")

    # 检查触发条件
    if status_code != 401 and "该令牌状态不可用" not in error_msg:
        return False

    logger.warning(
        f"检测到上游 Key 需要自动禁用: status={status_code}, "
        f"message={error_msg}"
    )

    from models.database import AsyncSessionLocal, UpstreamKey
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UpstreamKey).where(UpstreamKey.key == full_key)
        )
        up_key = result.scalars().first()

        if not up_key:
            logger.warning(
                f"自动禁用跳过: Key 不在数据库中 (可能是旧的环境变量注入)"
            )
            return False

        if up_key.status == "disabled":
            logger.info(f"Key '{up_key.name}' 已处于禁用状态，跳过")
            return False

        await disable_key_and_check_user_rate(db, up_key, error_msg)
        # 延迟导入避免循环依赖：key_disable ↔ management
        from router.management import _trigger_hot_reload as _thr
        await _thr(db)
        logger.info(f"自动禁用 Key Pool 已重建（401/令牌不可用）")

    return True
