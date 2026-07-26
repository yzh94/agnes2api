"""图片/视频 CDN 代理：绕过 CORS 限制，流式回传上游资源。

同时服务 /proxy/image（图片/视频 URL 代理）与视频 /v1/videos/{id}/content（复用 stream_proxy）。
注意：本端点不加 Bearer 鉴权（浏览器 <img>/<video> 无法带 Authorization），改用 IP 限流 + 域名白名单防滥用。
"""

import logging
import time
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from utils.http_client import get_http_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Proxy"])

# 已知的外部图片/视频域名，需要通过代理中转以绕过 CORS 限制
_PROXY_ALLOWED_HOSTS = {
    "platform-outputs.agnes-ai.space",
}

# 白名单中的文件扩展名
_PROXY_ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
    ".mp4", ".webm", ".mov",
}

_CONTENT_TYPE_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}

# 无扩展名时，按上游 Content-Type 前缀判定是否允许
_ALLOWED_CONTENT_TYPE_PREFIXES = ("image/", "video/")

# 每 IP 每分钟代理请求上限
_PROXY_RPM = 60


def _client_ip(request: Request) -> str:
    """获取客户端 IP（考虑 X-Forwarded-For）。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _check_proxy_rate_limit(request: Request) -> bool:
    """基于 IP 的简单固定窗口限流（内存）。超限返回 False。"""
    ip = _client_ip(request)
    # 简化：单进程下使用内存字典做简易限流
    try:
        bucket = int(time.time()) // 60
        limit_key = f"{ip}:{bucket}"
        if not hasattr(_check_proxy_rate_limit, '_counters'):
            _check_proxy_rate_limit._counters = {}
        current = _check_proxy_rate_limit._counters.get(limit_key, 0) + 1
        _check_proxy_rate_limit._counters[limit_key] = current
        return current <= _PROXY_RPM
    except Exception as e:
        logger.warning(f"Proxy rate limit check failed: {e}")
        return True


async def stream_proxy(
    url: str,
    request: Request,
    enforce_allowlist: bool = True,
) -> Response:
    """流式代理上游资源，支持 Range（206）与无扩展名 URL 的 Content-Type 回退。

    Args:
        url: 目标资源 URL
        request: FastAPI Request（用于读取 Range 头）
        enforce_allowlist: 是否强制域名白名单（/proxy/image 需要；/content 的 URL 来自上游结果也校验）
    """
    parsed = urlparse(url)

    # 安全检查：域名白名单
    if enforce_allowlist and parsed.hostname not in _PROXY_ALLOWED_HOSTS:
        logger.warning(f"Proxy rejected: hostname={parsed.hostname} not in allowlist")
        return JSONResponse(
            status_code=403,
            content={"error": "proxy_forbidden", "message": "Host not allowed"},
        )

    # 扩展名检查
    path_lower = parsed.path.lower()
    ext = path_lower[path_lower.rfind("."):] if "." in path_lower else ""
    if ext and ext not in _PROXY_ALLOWED_EXTENSIONS:
        logger.warning(f"Proxy rejected: extension={ext} not in allowlist")
        return JSONResponse(
            status_code=403,
            content={"error": "proxy_forbidden", "message": "File type not allowed"},
        )

    client = get_http_client()

    # 透传 Range 头（视频拖动 seek）
    headers: dict[str, str] = {}
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    try:
        req = client.build_request("GET", url, headers=headers)
        resp = await client.send(req, stream=True)
    except httpx.TimeoutException:
        logger.error(f"Proxy timeout: {url}")
        return JSONResponse(
            status_code=504,
            content={"error": "proxy_timeout", "message": "Upstream timeout"},
        )
    except Exception as e:
        logger.error(f"Proxy error: {url} | {e}")
        return JSONResponse(
            status_code=502,
            content={"error": "proxy_error", "message": str(e)},
        )

    if resp.status_code >= 400:
        await resp.aclose()
        logger.warning(f"Proxy upstream error: status={resp.status_code} url={url}")
        return JSONResponse(
            status_code=502,
            content={"error": "proxy_upstream_error", "message": f"Upstream returned {resp.status_code}"},
        )

    # 确定 content-type：有扩展名按扩展名；无扩展名按上游 Content-Type 回退判定
    if ext:
        content_type = _CONTENT_TYPE_MAP.get(ext, "application/octet-stream")
    else:
        upstream_ct = resp.headers.get("content-type", "")
        upstream_ct_main = upstream_ct.split(";")[0].strip().lower()
        if upstream_ct_main and any(
            upstream_ct_main.startswith(p) for p in _ALLOWED_CONTENT_TYPE_PREFIXES
        ):
            content_type = upstream_ct_main
        else:
            await resp.aclose()
            logger.warning(f"Proxy rejected: unsupported content-type={upstream_ct_main} url={url}")
            return JSONResponse(
                status_code=403,
                content={"error": "proxy_forbidden", "message": "Unsupported content type"},
            )

    # 响应头：透传 Range 相关字段
    resp_headers: dict[str, str] = {
        "Cache-Control": "public, max-age=86400",
        "Accept-Ranges": "bytes",
    }
    status_code = 200
    if resp.status_code == 206:
        status_code = 206
        cr = resp.headers.get("content-range")
        if cr:
            resp_headers["Content-Range"] = cr
    cl = resp.headers.get("content-length")
    if cl:
        resp_headers["Content-Length"] = cl

    async def stream_generator():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        except Exception as e:
            logger.error(f"Error while streaming proxy: {e}")
        finally:
            await resp.aclose()

    return StreamingResponse(
        stream_generator(),
        media_type=content_type,
        headers=resp_headers,
        status_code=status_code,
    )


@router.get("/proxy/image")
async def proxy_image(request: Request, url: str = Query(..., description="目标图片/视频的完整 URL")):
    """代理获取外部图片/视频，解决 CDN 无 CORS 头的问题。"""
    if not await _check_proxy_rate_limit(request):
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited", "message": "Too many proxy requests"},
        )
    return await stream_proxy(url, request, enforce_allowlist=True)
