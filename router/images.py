"""OpenAI 兼容的 /v1/images/generations 路由。"""

import asyncio
import base64
import logging
import traceback
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, Request

from config import settings
from models.openai import ImageRequest
from service.auth import verify_api_key
from service.errors import create_error_response
from service.model_guard import ensure_model_enabled
from service.transformer import UpstreamAPIError, call_agnes_generate
from utils.http_client import get_http_client

logger = logging.getLogger(__name__)

# 需要代理以绕过 CORS 的 CDN 域名
_CDN_HOSTNAME = "platform-outputs.agnes-ai.space"

# b64_json 抓取的容量与超时限制（防止大图 OOM / 挂起）
_B64_FETCH_TIMEOUT = 60.0
_B64_MAX_BYTES = 20 * 1024 * 1024  # 20 MB

router = APIRouter(
    prefix="/v1/images",
    tags=["Images"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/generations", response_model=None)
async def create_image(request: Request):
    """OpenAI 兼容的图像生成端点。

    接收 OpenAI Images API 格式的请求，转换后转发至 Agnes Image 2.1 Flash。
    """
    try:
        body = await request.json()
        # 解析为 OpenAI ImageRequest（允许未知扩展字段）
        openai_req = ImageRequest.model_validate(body)

        logger.info(
            f"Image generation request | model={openai_req.model} "
            f"size={openai_req.size} n={openai_req.n} "
            f"response_format={openai_req.response_format} "
            f"has_image={'yes' if openai_req.image else 'no'} "
            f"return_base64={openai_req.return_base64}"
        )

        model_error = await ensure_model_enabled(openai_req.model)
        if model_error:
            return create_error_response(
                detail=model_error,
                status_code=400,
                error_type="invalid_request_error",
                default_code="model_not_allowed",
            )

        # 调用 Agnes 上游
        user_id = getattr(request.state, 'user_id', 0)
        response = await call_agnes_generate(openai_req, user_id=user_id)

        logger.info(
            f"Image generation OK | images_returned={len(response.data)}"
        )

        resp_dict = response.model_dump(exclude_none=True)

        # 兼容 b64_json 格式：抓取图片并转 Base64
        if openai_req.response_format == "b64_json":
            client = get_http_client()

            async def _fetch_and_encode(item):
                orig_url = item.get("url")
                if not orig_url:
                    return item
                try:
                    img_resp = await client.get(orig_url, timeout=_B64_FETCH_TIMEOUT)
                    if img_resp.status_code != 200:
                        logger.warning(
                            f"b64_json fetch failed: status={img_resp.status_code} url={orig_url}"
                        )
                        return item
                    # 限制最大字节数，防止 OOM
                    cl = img_resp.headers.get("content-length")
                    if cl and int(cl) > _B64_MAX_BYTES:
                        logger.warning(f"b64_json skipped (too large): {cl}B url={orig_url}")
                        return item
                    content = img_resp.content
                    if len(content) > _B64_MAX_BYTES:
                        logger.warning(f"b64_json skipped (too large): {len(content)}B url={orig_url}")
                        return item
                    item["b64_json"] = base64.b64encode(content).decode("utf-8")
                    del item["url"]
                except Exception as e:
                    logger.warning(f"b64_json fetch error: {e} url={orig_url}")
                return item

            tasks = [_fetch_and_encode(item) for item in resp_dict.get("data", [])]
            resp_dict["data"] = await asyncio.gather(*tasks)
            return resp_dict

        # CDN 图片 URL 重写为代理 URL（仅当 IMAGE_URL_PROXY_MODE=on 时）
        # off（默认）：返回原始 CDN URL，对齐 OpenAI 规范
        if settings.image_url_proxy_mode == "on":
            base_url = str(request.base_url).rstrip("/")
            # 部署在反代后面时，按 X-Forwarded-Proto 修正协议，避免 Mixed Content
            if request.headers.get("x-forwarded-proto") == "https":
                base_url = base_url.replace("http://", "https://", 1)
            for item in resp_dict.get("data", []):
                orig_url = item.get("url")
                if orig_url and urlparse(orig_url).hostname == _CDN_HOSTNAME:
                    item["url"] = f"{base_url}/proxy/image?{urlencode({'url': orig_url})}"
        return resp_dict

    except UpstreamAPIError as e:
        logger.error(
            f"Upstream API error | status={e.status_code} detail={e.detail}"
        )
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="api_error",
            default_code="upstream_error",
        )

    except Exception:
        logger.exception("Unhandled internal server error")
        traceback.print_exc()
        return create_error_response(
            detail="Internal server error",
            status_code=500,
            error_type="server_error",
            default_code="internal_error",
        )
