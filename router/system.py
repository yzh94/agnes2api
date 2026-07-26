import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["System"])


@router.get("/health")
async def health():
    """健康检查端点。"""
    return {"status": "ok"}


@router.get("/health/keys")
async def health_check_keys():
    """获取所有 API Key 的状态信息。"""
    try:
        from service.simple_key_pool import get_key_pool_manager
        key_pool = get_key_pool_manager()
        keys_status = await key_pool.get_all_status()
        active_count = sum(1 for k in keys_status if k["status"] == "active")

        return {
            "status": "ok",
            "total_keys": len(keys_status),
            "active_keys": active_count,
            "degraded_keys": 0,
            "key_statuses": keys_status,
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": str(e)},
        )


@router.get("/api/stats")
async def get_stats():
    """获取所有 API Key 的请求统计信息。"""
    from service.key_stats import get_key_stats_manager

    stats_manager = get_key_stats_manager()
    all_stats = stats_manager.get_all_stats()
    total_stats = stats_manager.get_total_stats()

    return {
        "status": "ok",
        "keys": all_stats,
        "total": total_stats,
    }


@router.get("/api/stats/public")
async def get_stats_public():
    """获取所有 API Key 的请求统计信息（无需认证，用于前端加载）。"""
    from service.key_stats import get_key_stats_manager

    stats_manager = get_key_stats_manager()
    all_stats = stats_manager.get_all_stats()
    total_stats = stats_manager.get_total_stats()

    return {
        "status": "ok",
        "keys": all_stats,
        "total": total_stats,
    }
