"""模型白名单校验。

仅允许请求使用管理端配置且处于启用状态的模型。
未命中时返回 OpenAI 兼容错误。
"""

import logging

from sqlalchemy import select

from models.database import AsyncSessionLocal, AvailableModel

logger = logging.getLogger(__name__)


def normalize_requested_model(model: str | None) -> str:
    """规范化客户端请求模型名。"""
    return (model or "").strip()


async def is_model_enabled(model: str | None) -> bool:
    """检查模型是否在管理端启用。"""
    normalized_model = normalize_requested_model(model)
    if not normalized_model:
        return False

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AvailableModel.id).where(
                AvailableModel.name == normalized_model,
                AvailableModel.is_active == True,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None


async def ensure_model_enabled(model: str | None) -> str | None:
    """校验模型是否可用，不可用时返回错误消息。"""
    normalized_model = normalize_requested_model(model)
    if not normalized_model:
        return "Model is required."

    if await is_model_enabled(normalized_model):
        return None

    logger.warning("Rejected request for unavailable model: %s", normalized_model)
    return f"The model `{normalized_model}` is not available for this service."
