"""Agnes Image 2.1 Flash → OpenAI 兼容中转服务入口。

启动：python main.py  或  uvicorn main:app --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
import sys
from urllib.parse import urlparse

import httpx
from contextlib import asynccontextmanager
from utils.http_client import get_http_client, close_http_client
import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, JSONResponse, Response

from config import settings
from models.openai import ErrorDetail, ErrorResponse
from router.images import router as images_router
from router.chat import router as chat_router
from router.completions import router as completions_router
from router.key_pool import router as router_key_pool
from router.video import router as video_router, router_v1_videos
from router.responses import router as responses_router
from router.proxy import router as proxy_router
from router.system import router as system_router
from router.frontend import router as frontend_router
from router.models import router as native_models_router
from router.gemini import router as gemini_router
from service.auth import AuthenticationError, verify_api_key
from service.video import VideoServiceError

# ---------- 日志配置 ----------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# 降低 httpx 的日志级别，避免输出 HTTP 请求详情
logging.getLogger("httpx").setLevel(logging.WARNING)

# 先定义 lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ================== STARTUP ==================
    logger.info(
        f"Agnes2API starting on {settings.server_host}:{settings.server_port}"
    )
    logger.info(f"Agnes base URL: {settings.agnes_base_url}")
    logger.info(
        f"Server API key auth: {'enabled' if settings.server_api_key else 'disabled'}"
    )

    # 初始化数据库
    try:
        from models.database import init_db
        await init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise SystemExit(1)

    # 从数据库加载 Upstream Keys
    from models.database import AsyncSessionLocal, UpstreamKey
    from sqlalchemy import select
    all_keys = []
    active_keys = []
    key_statuses: dict[str, dict] = {}

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UpstreamKey))
        db_keys = result.scalars().all()

        if not db_keys:
            logger.warning("UpstreamKey table is empty. Please configure keys via the management UI.")
        else:
            logger.info("Loading upstream keys from database...")
            # 以 MySQL 状态为准重建 Redis：保留 disabled 状态（不再启动时强制启用，
            # 真正失效的 Key 由定时失败巡检恢复）。
            from service.redis_key_pool import get_key_pool_manager as _gkpm
            _kp = _gkpm()
            for k in db_keys:
                all_keys.append(k.key)
                if k.status == "active":
                    active_keys.append(k.key)
                masked = _kp._compute_key_prefix(k.key)
                disabled_at_ts = ""
                if k.disabled_at:
                    try:
                        disabled_at_ts = str(int(k.disabled_at.timestamp()))
                    except Exception:
                        disabled_at_ts = ""
                key_statuses[masked] = {
                    "status": k.status,
                    "disabled_at": disabled_at_ts,
                    "disabled_reason": k.disabled_reason or "",
                }

    if not active_keys:
        logger.warning("No active upstream keys found! The service will not be able to process requests.")

    # 初始化 API Key 统计管理器（基于 Redis）
    from service.key_stats import get_key_stats_manager
    stats_manager = get_key_stats_manager()
    for key_str in active_keys:
        stats_manager.register_key(key_str)
    logger.info(f"Key stats manager initialized with {len(active_keys)} keys")

    # 初始化 Redis Key Pool（LRU 轮询 + 二态）：以 MySQL 状态为准还原 active/disabled
    from service.redis_key_pool import get_key_pool_manager
    key_pool = get_key_pool_manager()
    await key_pool.initialize(all_keys, key_statuses=key_statuses)
    logger.info("Redis Key Pool Manager initialized (LRU mode)")

    # 启动时对账：清扫 Redis 中 DB 已不存在的上游 Key 的孤儿数据
    try:
        from service.redis_reconcile import reconcile_upstream_keys_with_db
        async with AsyncSessionLocal() as session:
            await reconcile_upstream_keys_with_db(session)
    except Exception as e:
        logger.warning(f"启动对账失败（不阻断启动）: {e}")

    # 启动时同步系统配置（速率限制）到 Redis
    try:
        async with AsyncSessionLocal() as session:
            from service.system_config import ensure_system_config_initialized
            await ensure_system_config_initialized(session)
    except Exception as e:
        logger.warning(f"同步系统配置失败（不阻断启动）: {e}")

    # 启动统计每日重置调度器
    stats_scheduler = None
    if settings.stats_daily_reset_enabled:
        from service.stats_scheduler import StatsDailyResetScheduler
        stats_scheduler = StatsDailyResetScheduler(settings.stats_daily_reset_time)
        stats_scheduler.start()
        logger.info(f"Stats daily reset scheduler started, reset at {settings.stats_daily_reset_time}")

    # 启动上游 Key 失败巡检调度器
    key_validation_scheduler = None
    if settings.upstream_key_validation_enabled:
        from service.key_validation_scheduler import KeyValidationScheduler
        key_validation_scheduler = KeyValidationScheduler(
            settings.upstream_key_validation_interval_minutes, concurrency=100
        )
        key_validation_scheduler.start()
        logger.info(
            f"Upstream key validation scheduler started, interval="
            f"{settings.upstream_key_validation_interval_minutes}min"
        )

    # 启动 Redis → MySQL 状态同步调度器
    redis_sync_scheduler = None
    if settings.upstream_key_redis_sync_enabled:
        from service.redis_to_mysql_sync import RedisToMySQLSyncScheduler
        redis_sync_scheduler = RedisToMySQLSyncScheduler(
            settings.upstream_key_redis_sync_interval_minutes
        )
        redis_sync_scheduler.start()
        logger.info(
            f"Redis→MySQL sync scheduler started, interval="
            f"{settings.upstream_key_redis_sync_interval_minutes}min"
        )

    # 启动后延迟触发一次失败 Key 巡检：保留「重启恢复」语义。
    # 与原版「启动强制启用所有 disabled key」不同，这里实际检验一遍，
    # 通过才恢复，避免把真正失效的 Key 误放回路由。延迟 30s 等服务稳定。
    if settings.upstream_key_validation_enabled:
        async def _startup_validation():
            await asyncio.sleep(30)
            try:
                from service.key_validation import run_full_validation
                from models.database import AsyncSessionLocal
                async with AsyncSessionLocal() as session:
                    data = await run_full_validation(session, concurrency=100)
                s = data.get("summary", {})
                logger.info(
                    f"[启动巡检] 完成: 总计 {s.get('total', 0)} "
                    f"通过 {s.get('success', 0)} 失败 {s.get('failed', 0)}"
                )
            except Exception as e:
                logger.warning(f"启动失败 Key 巡检异常（不影响服务）: {e}")

        asyncio.create_task(_startup_validation())

    get_http_client()

    yield

    # ================== SHUTDOWN ==================
    try:
        if stats_scheduler:
            await stats_scheduler.stop()
        if key_validation_scheduler:
            await key_validation_scheduler.stop()
        if redis_sync_scheduler:
            await redis_sync_scheduler.stop()
        logger.info("Redis Key Pool Manager stopped")
        await close_http_client()
        from service.llm_content_logger import get_llm_content_logger
        get_llm_content_logger().close()
        logger.info("LLM content logger closed")
    except Exception as e:
        logger.warning(f"Shutdown cleanup error: {e}")

app = FastAPI(
    title="Agnes2API",
    lifespan=lifespan,
    description="OpenAI 兼容的 Agnes Image 2.1 Flash 中转服务",
    version="1.0.0",
)

# CORS 中间件，允许任意来源调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,  # 缓存预检请求 24 小时
)

app.include_router(images_router)
app.include_router(chat_router)
app.include_router(completions_router)
app.include_router(responses_router)
app.include_router(router_key_pool)
app.include_router(video_router)
app.include_router(router_v1_videos)
app.include_router(native_models_router)
app.include_router(gemini_router)
app.include_router(proxy_router)
app.include_router(system_router)
from router.discord_auth import router as discord_auth_router
app.include_router(discord_auth_router, prefix="/api/manage")
from router.management import router as management_router
app.include_router(management_router)
app.include_router(frontend_router)


# ---------- 请求 / 响应日志中间件 ----------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录每个 HTTP 请求的方法、路径、状态码和处理时间。"""
    logger.debug(f"--> {request.method} {request.url.path}")
    response = await call_next(request)
    logger.debug(
        f"<-- {request.method} {request.url.path} → {response.status_code}"
    )
    return response


# ---------- OpenAI 兼容的认证错误处理 ----------


@app.exception_handler(AuthenticationError)
async def authentication_exception_handler(request: Request, exc: AuthenticationError):
    """将认证错误转换为 OpenAI 兼容错误格式：
    {"error": {"message": "...", "type": "...", "code": "..."}}
    """
    logger.warning(f"Auth failed: {exc.message} (code={exc.code})")
    return ORJSONResponse(
        status_code=401,
        content=ErrorResponse(
            error=ErrorDetail(
                message=exc.message,
                type="authentication_error",
                code=exc.code,
            )
        ).model_dump(exclude_none=True),
    )


@app.exception_handler(VideoServiceError)
async def video_service_error_handler(request: Request, exc: VideoServiceError):
    """将视频服务错误转换为 OpenAI 兼容错误格式：
    {"error": {"message": "...", "type": "...", "code": "..."}}
    """
    logger.warning(f"Video service error: {exc.detail}")
    
    # 解析 detail，如果是字典则直接使用，否则构造标准格式
    detail = exc.detail
    if isinstance(detail, dict):
        error_body = {
            "error": {
                "message": detail.get("message", str(exc)),
                "type": detail.get("type", "video_error"),
                "code": detail.get("code"),
            }
        }
    else:
        error_body = {
            "error": {
                "message": str(detail),
                "type": "video_error",
                "code": "video_error",
            }
        }
    
    return ORJSONResponse(
        status_code=exc.status_code,
        content=error_body,
    )



    







if __name__ == "__main__":
    import os
    
    # 开发环境：启用热重载
    # 生产环境：禁用热重载，启用 workers
    is_dev = os.environ.get("DEV_MODE", "false").lower() == "true"
    
    if is_dev:
        logger.info("Starting server in DEVELOPMENT mode...")
        uvicorn.run(
            "main:app",
            host=settings.server_host,
            port=settings.server_port,
            reload=True,  # 开发模式：文件变更自动重启
        )
    else:
        logger.info("Starting server in PRODUCTION mode...")
        uvicorn.run(
            "main:app",
            host=settings.server_host,
            port=settings.server_port,
            proxy_headers=True,
            forwarded_allow_ips="*",
            reload=False,  # 生产模式：禁用热重载
            workers=int(os.environ.get("UVICORN_WORKERS", 1)),  # 可通过环境变量配置 worker 数
        )
