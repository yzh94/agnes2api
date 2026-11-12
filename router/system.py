import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["System"])

@router.get("/health")
async def health():
    """健康检查端点。"""
    logger.debug("Health check called")
    return {"status": "ok"}


@router.get("/health/keys")
async def health_check_keys():
    """获取所有 API Key 的状态信息（key 已模糊隐藏，不暴露完整密钥）。"""
    try:
        from service.redis_key_pool import get_key_pool_manager
        key_pool = get_key_pool_manager()
        status = await key_pool.get_pool_status()

        return {
            "status": status["status"],
            "total_keys": status["total_keys"],
            "active_keys": status["active_keys"],
            "disabled_keys": status["disabled_keys"],
            "key_statuses": status.get("keys", []),
        }
    except RuntimeError as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": str(e)},
        )

@router.get("/api/stats")
async def get_stats():
    """获取所有 API Key 的请求统计信息（按模型类型分类）。"""
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


@router.get("/api/announcements")
async def get_public_announcements():
    """获取所有启用的公告（无需认证，供前端首页展示）。"""
    from models.database import AsyncSessionLocal, Announcement
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Announcement)
            .where(Announcement.is_active == True)
            .order_by(
                Announcement.is_pinned.desc(),
                Announcement.sort_order.asc(),
                Announcement.created_at.desc()
            )
        )
        announcements = result.scalars().all()
        return [
            {
                "id": a.id,
                "title": a.title,
                "content": a.content,
                "is_pinned": a.is_pinned,
                "sort_order": a.sort_order,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            }
            for a in announcements
        ]
