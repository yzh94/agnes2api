"""Agnes2API → OpenAI 兼容中转服务入口。

启动：python main.py  或  uvicorn main:app --host 0.0.0.0 --port 8000
"""

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
from router.key_pool import router as router_key_pool
from router.video import router as video_router, router_v1_videos
from router.proxy import router as proxy_router
from router.system import router as system_router
from router.frontend import router as frontend_router
from router.models import router as native_models_router
from router.gemini import router as gemini_router
from service.auth import AuthenticationError
from service.video import VideoServiceError

# ---------- 日志配置 ----------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


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
        from models.database import init_db, seed_defaults, AsyncSessionLocal
        await init_db()
        async with AsyncSessionLocal() as session:
            await seed_defaults()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    # 从数据库加载 Upstream Keys
    from models.database import AsyncSessionLocal, UpstreamKey
    from sqlalchemy import select
    active_keys = []

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UpstreamKey))
        db_keys = result.scalars().all()

        if not db_keys:
            logger.warning("UpstreamKey table is empty. Please configure keys via the management UI.")
        else:
            logger.info("Loading upstream keys from database...")
            active_keys = [{"key": k.key, "weight": k.weight} for k in db_keys if k.status == "active"]

    if not active_keys:
        logger.warning("No active upstream keys found! The service will not be able to process requests.")

    # 初始化 Key Pool Manager（内存版）
    from service.simple_key_pool import get_key_pool_manager
    key_pool = get_key_pool_manager()
    await key_pool.initialize(active_keys)
    logger.info("Simple Key Pool Manager initialized")

    # 初始化 API Key 统计管理器（纯内存）
    from service.key_stats import get_key_stats_manager
    stats_manager = get_key_stats_manager()
    for key_info in active_keys:
        stats_manager.register_key(key_info["key"])
    logger.info(f"Key stats manager initialized with {len(active_keys)} keys")

    get_http_client()

    yield

    # ================== SHUTDOWN ==================
    try:
        await close_http_client()
    except Exception as e:
        logger.warning(f"Shutdown cleanup error: {e}")


app = FastAPI(
    title="Agnes2API",
    lifespan=lifespan,
    description="OpenAI 兼容的 Agnes Image/Video/Chat 中转服务",
    version="1.0.0",
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,
)

app.include_router(images_router)
app.include_router(chat_router)
app.include_router(router_key_pool)
app.include_router(video_router)
app.include_router(router_v1_videos)
app.include_router(native_models_router)
app.include_router(gemini_router)
app.include_router(proxy_router)
app.include_router(system_router)
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
    """将认证错误转换为 OpenAI 兼容错误格式。"""
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
    """将视频服务错误转换为 OpenAI 兼容错误格式。"""
    logger.warning(f"Video service error: {exc.detail}")

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

    is_dev = os.environ.get("DEV_MODE", "false").lower() == "true"

    if is_dev:
        logger.info("Starting server in DEVELOPMENT mode...")
        uvicorn.run(
            "main:app",
            host=settings.server_host,
            port=settings.server_port,
            reload=True,
        )
    else:
        logger.info("Starting server in PRODUCTION mode...")
        uvicorn.run(
            "main:app",
            host=settings.server_host,
            port=settings.server_port,
            proxy_headers=True,
            forwarded_allow_ips="*",
            reload=False,
            workers=int(os.environ.get("UVICORN_WORKERS", 1)),
        )
