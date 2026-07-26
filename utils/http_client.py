import httpx
from typing import Optional
from config import settings
import logging

logger = logging.getLogger(__name__)

_global_client: Optional[httpx.AsyncClient] = None

def get_http_client() -> httpx.AsyncClient:
    """获取全局共享的 HTTP 客户端实例，实现连接池复用。"""
    global _global_client
    if _global_client is None or _global_client.is_closed:
        limits = httpx.Limits(
            max_keepalive_connections=200, 
            max_connections=500,
            keepalive_expiry=30.0
        )
        timeout = httpx.Timeout(settings.request_timeout)
        _global_client = httpx.AsyncClient(timeout=timeout, limits=limits, http2=True)
        logger.info("Global HTTP client created")
    return _global_client

async def close_http_client():
    """关闭全局 HTTP 客户端。"""
    global _global_client
    if _global_client is not None and not _global_client.is_closed:
        await _global_client.aclose()
        _global_client = None
        logger.info("Global HTTP client closed")
