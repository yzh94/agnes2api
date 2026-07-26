"""API Key Pool 管理接口（简化版，基于内存）。

提供 Key 池状态查询。
"""

import logging

from fastapi import APIRouter, Depends

from service.auth import verify_api_key
from service.simple_key_pool import get_key_pool_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/keys", tags=["Key Pool"], dependencies=[Depends(verify_api_key)])


@router.get("/pool")
async def get_pool_status():
    """获取 Key 池状态。"""
    try:
        key_pool = get_key_pool_manager()
        keys_status = await key_pool.get_all_status()
        active_count = sum(1 for k in keys_status if k["status"] == "active")
        return {
            "status": "ok",
            "total_keys": len(keys_status),
            "active_keys": active_count,
            "degraded_keys": 0,
            "rotation_list_length": len(key_pool._rotation_list),
            "degraded_queue_length": 0,
            "keys": keys_status,
        }
    except Exception as e:
        logger.error(f"获取 Key 池状态失败: {e}")
        return {
            "status": "error",
            "message": str(e),
            "keys": [],
        }
