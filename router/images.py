"""OpenAI 兼容的 /v1/images/generations 路由。"""

import asyncio
import base64
import ipaddress
import logging
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from config import settings
from models.openai import ImageRequest
from service.auth import verify_api_key
from service.errors import create_error_response
from service.model_guard import ensure_model_enabled
from service.transformer import UpstreamAPIError, call_agnes_generate
from utils.http_client import get_http_client

logger = logging.getLogger(__name__)

# 需要代理以绕过 CORS 的 CDN 域名（不再硬编码域名：改为按"外部地址"判定，见 _is_external_url）

# b64_json 抓取的容量与超时限制（防止大图 OOM / 挂起）
_B64_FETCH_TIMEOUT = 60.0
_B64_MAX_BYTES = 20 * 1024 * 1024  # 20 MB

router = APIRouter(
    prefix="/v1/images",
    tags=["Images"],
    dependencies=[Depends(verify_api_key)],
)


def _is_external_url(url: str, self_hostname: str) -> bool:
    """判断 URL 是否为需要代理的外部 http/https 地址（域名无关，自动适配 CDN 变更）。

    - 仅接受 http/https
    - 排除本服务自身 host（防死循环重写）
    - 排除回环 / 链路本地 / 内网 / 保留地址（防止把内网地址重写成代理暴露）
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host or parsed.scheme not in ("http", "https"):
        return False
    host_lower = host.lower()
    if host_lower == self_hostname.lower() or host_lower in ("localhost", "0.0.0.0"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # 普通域名：视为外部地址
        return True
    return not (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _finalize_image_response(
    resp_dict: dict,
    response_format: str | None,
    request: Request,
) -> dict:
    """统一处理图像响应：b64_json 抓取转码与 CDN URL 代理重写。"""
    # 兼容 b64_json 格式：抓取图片并转 Base64
    if response_format == "b64_json":
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
        self_hostname = urlparse(base_url).hostname or ""
        for item in resp_dict.get("data", []):
            orig_url = item.get("url")
            if orig_url and _is_external_url(orig_url, self_hostname):
                item["url"] = f"{base_url}/proxy/image?{urlencode({'url': orig_url})}"
    return resp_dict


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

        # 确定实际期望的输出格式，以便在 _finalize_image_response 中准确执行 b64 Fallback 抓取和重写
        resolved_format = openai_req.response_format
        if not resolved_format:
            if openai_req.extra_body and isinstance(openai_req.extra_body, dict):
                resolved_format = openai_req.extra_body.get("response_format")
            if not resolved_format and openai_req.return_base64:
                resolved_format = "b64_json"

        resp_dict = response.model_dump(exclude_none=True)
        return await _finalize_image_response(resp_dict, resolved_format, request)

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
        return create_error_response(
            detail="Internal server error",
            status_code=500,
            error_type="server_error",
            default_code="internal_error",
        )


@router.post("/edits", response_model=None)
async def create_image_edit(
    request: Request,
    image: UploadFile = File(..., description="要编辑的输入图像文件"),
    prompt: str = Form(..., description="编辑指令"),
    model: str | None = Form(default=None, description="模型名称"),
    size: str = Form(default="1024x1024", description="输出尺寸"),
    n: int = Form(default=1, ge=1, le=10, description="生成数量"),
    response_format: str | None = Form(default=None, description="url 或 b64_json"),
    user: str | None = Form(default=None, description="用户标识"),
):
    """OpenAI 兼容的图像编辑端点（multipart/form-data）。

    接收上传的图像文件，转 Data URI Base64 后通过 Agnes 图生图能力实现编辑。
    """
    try:
        target_model = model or "agnes-image-2.1-flash"

        model_error = await ensure_model_enabled(target_model)
        if model_error:
            return create_error_response(
                detail=model_error,
                status_code=400,
                error_type="invalid_request_error",
                default_code="model_not_allowed",
            )

        content = await image.read()
        if not content:
            return create_error_response(
                detail="Uploaded image file is empty.",
                status_code=400,
                error_type="invalid_request_error",
                default_code="empty_image",
            )
        if len(content) > _B64_MAX_BYTES:
            return create_error_response(
                detail="Uploaded image file is too large (max 20 MB).",
                status_code=400,
                error_type="invalid_request_error",
                default_code="image_too_large",
            )

        content_type = image.content_type or "image/png"
        data_uri = f"data:{content_type};base64,{base64.b64encode(content).decode('utf-8')}"

        openai_req = ImageRequest(
            model=target_model,
            prompt=prompt,
            size=size,
            n=n,
            response_format=response_format,
            image=[data_uri],
        )

        logger.info(
            f"Image edit request | model={target_model} size={size} n={n} "
            f"response_format={response_format} file={image.filename}"
        )

        user_id = getattr(request.state, 'user_id', 0)
        response = await call_agnes_generate(openai_req, user_id=user_id)
        resp_dict = response.model_dump(exclude_none=True)
        return await _finalize_image_response(resp_dict, response_format, request)

    except UpstreamAPIError as e:
        logger.error(f"Upstream API error | status={e.status_code} detail={e.detail}")
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="api_error",
            default_code="upstream_error",
        )

    except Exception:
        logger.exception("Unhandled internal server error")
        return create_error_response(
            detail="Internal server error",
            status_code=500,
            error_type="server_error",
            default_code="internal_error",
        )
