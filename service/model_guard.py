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


async def get_model_type(model: str | None) -> str | None:
    """返回模型的 type 字段（text/image/video）。未配置时返回 None。"""
    normalized_model = normalize_requested_model(model)
    if not normalized_model:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AvailableModel.type).where(AvailableModel.name == normalized_model).limit(1)
        )
        row = result.scalar_one_or_none()
        return row if isinstance(row, str) else None


async def ensure_text_model(model: str | None) -> str | None:
    """确保模型可用于文本接口（chat/completions）。

    返回 None 表示通过；返回错误消息则应直接拒绝。
    """
    # 先检查是否启用
    enabled_err = await ensure_model_enabled(model)
    if enabled_err:
        return enabled_err

    model_type = await get_model_type(model)
    if model_type and model_type not in ("text", "shared"):
        logger.warning("Rejected non-text model in text endpoint: %s type=%s", model, model_type)
        return f"The model `{model}` is a {model_type} model and cannot be used for text completion."

    return None
