"""请求 / 响应转换器：OpenAI Images API ⇄ Agnes Image 2.1 Flash。

优化功能：
- 并行调用支持（n>1 时并行发送请求）
- 请求缓存（LRU + TTL）
- 详细性能日志
"""

import asyncio
import json
from service.upstream_client import request_upstream_with_retry
from service.errors import UpstreamAPIError
import logging
import time
from typing import Any

import httpx

from config import settings
from service.simple_key_pool import get_key_pool_manager
from service.key_stats import get_key_stats_manager
from models.agnes import AgnesExtraBody, AgnesImageRequest
from models.openai import ImageData, ImageRequest, ImageResponse, ImageUsage

logger = logging.getLogger(__name__)


# ---------- 异常 ----------


class UpstreamAPIError(Exception):
    """上游 Agnes API 错误。"""

    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Upstream API error {status_code}")


# ---------- 请求转换 ----------


def _openai_request_to_agnes_request(req: ImageRequest) -> AgnesImageRequest:
    """将 OpenAI 标准请求转换为 Agnes 上游请求。"""

    extra_body = AgnesExtraBody()

    # 1) response_format: 从顶层移到 extra_body
    if req.response_format:
        extra_body.response_format = req.response_format

    # 2) image 数组: 映射到 extra_body.image（图生图）
    if req.image:
        extra_body.image = req.image

    # 3) 如果 extra_body 非空才赋值，避免发送空对象
    agnes_req = AgnesImageRequest(
        model=req.model,
        prompt=req.prompt,
        size=req.size,
    )

    # 文生图 Base64 输出使用顶层 return_base64
    if req.return_base64 is not None:
        agnes_req.return_base64 = req.return_base64
    # 图生图 Base64 输出：用户传入 response_format=b64_json 时，已在 extra_body.response_format 中
    # 但文生图 Base64 应当使用 return_base64=true，而非 extra_body.response_format=b64_json
    if not req.image and req.response_format == "b64_json":
        # 纯文生图 + Base64 输出 → 使用 return_base64
        agnes_req.return_base64 = True
        extra_body.response_format = None

    # 仅在 extra_body 有实际字段时才设置
    if extra_body.response_format or extra_body.image:
        agnes_req.extra_body = extra_body

    return agnes_req


def _build_agnes_payload(req: ImageRequest) -> dict[str, Any]:
    """构建发送到 Agnes 的 JSON payload 字典。"""

    agnes_req = _openai_request_to_agnes_request(req)
    payload = agnes_req.model_dump(exclude_none=True, by_alias=True)
    return payload


# ---------- 响应转换 ----------


def _agnes_data_to_openai_data(agnes_data_list: list[dict[str, Any]]) -> list[ImageData]:
    """将 Agnes 返回的 data[] 转换为 OpenAI 格式，仅保留非空字段。"""

    result: list[ImageData] = []
    for item in agnes_data_list:
        kwargs: dict[str, Any] = {}
        if item.get("url"):
            kwargs["url"] = item["url"]
        if item.get("b64_json"):
            kwargs["b64_json"] = item["b64_json"]
        if item.get("revised_prompt"):
            kwargs["revised_prompt"] = item["revised_prompt"]
        result.append(ImageData(**kwargs))
    return result


def _agnes_response_to_openai_response(
    agnes_resp: dict[str, Any],
) -> ImageResponse:
    """将 Agnes 响应转换为 OpenAI 兼容响应。"""

    created = agnes_resp.get("created", int(time.time()))
    data = _agnes_data_to_openai_data(agnes_resp.get("data", []))
    resp = ImageResponse(created=created, data=data)

    # usage 透传（gpt-image-1 等上游返回 token 用量时）
    usage_data = agnes_resp.get("usage")
    if isinstance(usage_data, dict) and usage_data:
        resp.usage = ImageUsage(
            input_tokens=usage_data.get("input_tokens"),
            output_tokens=usage_data.get("output_tokens"),
            total_tokens=usage_data.get("total_tokens"),
        )
    return resp


# ---------- 上游调用 ----------


async def _single_image_call(
    payload: dict[str, Any],
    index: int,
    user_id: int = 0,
) -> dict[str, Any]:
    """单次图片生成请求（用于并行调用）。

    使用统一封装的 request_upstream_with_retry：失败自动换 Key 重试，
    成功时返回实际成功的那把 Key，保证“请求成功的 Key”与“响应使用的 Key”一致。
    """
    t_start = time.monotonic()

    # request_upstream_with_retry 内部自带换 Key 重试与 401 禁用逻辑，
    # 返回的 used_key 是实际成功的那把 Key（而非外层预先取的 Key）。
    http_resp, used_key = await request_upstream_with_retry(
        method="POST",
        url_template=f"{settings.agnes_base_url}/v1/images/generations",
        model_type="image",
        payload=payload,
        max_retries=1,
        user_id=user_id,
    )

    elapsed_ms = (time.monotonic() - t_start) * 1000
    key_pool = get_key_pool_manager()
    masked_key = key_pool._compute_key_prefix(used_key)

    return {
        "index": index,
        "payload": payload,
        "response": http_resp.json(),
        "elapsed_ms": elapsed_ms,
        "api_key": masked_key,  # 实际成功的那把 Key
    }


async def call_agnes_generate(req: ImageRequest, user_id: int = 0) -> ImageResponse:
    """调用 Agnes Image 2.1 Flash 上游 API，返回 OpenAI 兼容响应。

    优化功能：
    - 并行调用：当 enable_parallel_calls=True 且 n>1 时，并行发送 n 个请求
    - 请求缓存：相同请求直接返回缓存结果
    """
    n = max(req.n, 1)
    payload = _build_agnes_payload(req)

    logger.info(
        f"Calling Agnes upstream | url={settings.agnes_base_url} "
        f"n={n} parallel={settings.enable_parallel_calls} "
        f"timeout={settings.request_timeout}s"
    )
    logger.debug(f"Agnes payload: {payload}")

    t_total_start = time.monotonic()

    try:
        if settings.enable_parallel_calls and n > 1:
            # 并行调用：同时发送 n 个请求；单张失败不影响其余，聚合部分成功
            logger.info(f"Parallel mode: sending {n} concurrent requests")
            tasks = [_single_image_call(payload, i, user_id) for i in range(n)]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            results = []
            last_error = None
            for r in raw_results:
                if isinstance(r, BaseException):
                    logger.error(f"Parallel image call failed: {r}")
                    if isinstance(r, UpstreamAPIError):
                        last_error = r
                    continue
                results.append(r)
            if not results:
                # 全部失败：抛出最后一个上游错误
                raise last_error if last_error else UpstreamAPIError(
                    status_code=500, detail="All parallel image calls failed"
                )
        else:
            # 串行调用：逐个发送请求
            logger.info(f"Serial mode: sending {n} requests sequentially")
            results = []
            for i in range(n):
                result = await _single_image_call(payload, i, user_id)
                results.append(result)

    except UpstreamAPIError as e:
        total_elapsed = (time.monotonic() - t_total_start) * 1000
        logger.error(f"[{total_elapsed:.0f}ms] Upstream API error: {e.status_code}")
        raise

    # 合并结果
    all_data: list[ImageData] = []
    created = int(time.time())
    total_elapsed = (time.monotonic() - t_total_start) * 1000

    for result in results:
        agnes_response = _agnes_response_to_openai_response(result["response"])
        all_data.extend(agnes_response.data)
        created = agnes_response.created
        logger.info(
            f"Request {result['index'] + 1}/{n} done | "
            f"images={len(agnes_response.data)} "
            f"elapsed={result['elapsed_ms']:.0f}ms"
        )

    logger.info(
        f"Upstream calls complete | total_images={len(all_data)} "
        f"requests_sent={n} total_time={total_elapsed:.0f}ms"
    )

    return ImageResponse(created=created, data=all_data)