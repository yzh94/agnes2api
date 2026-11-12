"""API Key Pool 管理接口。

提供 Key 池状态查询、手动激活/禁用、状态重置等管理功能。
Key 池为二态模型（active | disabled），LRU 轮询，失败即禁用，
巡检通过后恢复。
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

from service.redis_key_pool import get_key_pool_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/keys", tags=["Key Pool"])


# ---------- 请求/响应模型 ----------


class KeyStatusResponse(BaseModel):
    """Key 状态响应（二态）。"""
    key_prefix: str
    status: str  # active | disabled
    prefix_type: str  # cpk | sk | other
    last_used_at: Optional[str] = None  # ISO 8601 (UTC)
    disabled_at: Optional[str] = None
    disabled_reason: Optional[str] = None
    total_success: int = 0
    total_failure: int = 0
    recent_success_rate: Optional[float] = None  # 近期滑动窗口成功率 (%)
    recent_samples: int = 0  # 窗口样本数


class PoolStatusResponse(BaseModel):
    """Key 池状态响应。"""
    status: str
    total_keys: int
    active_keys: int
    disabled_keys: int
    failure_reasons: dict = Field(default_factory=dict)  # 失败原因分类计数
    keys: list[KeyStatusResponse]


class ActivateResponse(BaseModel):
    """激活响应。"""
    status: str
    message: str


class ResetResponse(BaseModel):
    """重置响应。"""
    status: str
    message: str


# ---------- API 端点 ----------


@router.get("/pool", response_model=PoolStatusResponse)
async def get_pool_status():
    """获取 Key 池状态。

    返回所有 Key 的二态状态、成功/失败计数、失败原因分类等信息。
    """
    try:
        key_pool = get_key_pool_manager()
        status = await key_pool.get_pool_status()

        return PoolStatusResponse(
            status=status["status"],
            total_keys=status["total_keys"],
            active_keys=status["active_keys"],
            disabled_keys=status["disabled_keys"],
            failure_reasons=status.get("failure_reasons", {}),
            keys=[
                KeyStatusResponse(**k) for k in status.get("keys", [])
            ],
        )
    except Exception as e:
        logger.error(f"获取 Key 池状态失败: {e}")
        return PoolStatusResponse(
            status="error",
            total_keys=0,
            active_keys=0,
            disabled_keys=0,
            keys=[],
        )


@router.post("/{key_prefix}/activate", response_model=ActivateResponse)
async def activate_key(key_prefix: str):
    """手动激活指定 Key。

    将指定 Key 恢复为活跃状态，last_used_at 更新为当前时刻
    （按 LRU 规则从队尾重新排队）。
    """
    try:
        key_pool = get_key_pool_manager()
        await key_pool.activate_key(key_prefix)
        return ActivateResponse(
            status="ok",
            message=f"Key {key_prefix} 已激活",
        )
    except Exception as e:
        logger.error(f"激活 Key {key_prefix} 失败: {e}")
        return ActivateResponse(
            status="error",
            message=f"激活失败: {str(e)}",
        )


@router.post("/{key_prefix}/disable", response_model=ActivateResponse)
async def disable_key(key_prefix: str):
    """手动禁用指定 Key。

    将指定 Key 强制设置为禁用状态，不再参与轮询。
    """
    try:
        key_pool = get_key_pool_manager()
        await key_pool.force_disable(key_prefix)
        return ActivateResponse(
            status="ok",
            message=f"Key {key_prefix} 已手动禁用",
        )
    except Exception as e:
        logger.error(f"禁用 Key {key_prefix} 失败: {e}")
        return ActivateResponse(
            status="error",
            message=f"禁用失败: {str(e)}",
        )


@router.post("/reset", response_model=ResetResponse)
async def reset_all_keys():
    """重置所有 Key 状态。

    将所有 Key 恢复为活跃状态，保留计数与 last_used_at。
    """
    try:
        key_pool = get_key_pool_manager()
        await key_pool.reset_all_keys()
        return ResetResponse(
            status="ok",
            message="所有 Key 状态已重置",
        )
    except Exception as e:
        logger.error(f"重置所有 Key 失败: {e}")
        return ResetResponse(
            status="error",
            message=f"重置失败: {str(e)}",
        )
