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
from typing import Any, Optional

import httpx

from config import settings
from service.redis_key_pool import get_key_pool_manager
from service.cache import request_cache, generate_image_cache_key
from service.key_stats import get_key_stats_manager
from models.agnes import AgnesExtraBody, AgnesImageRequest
from models.openai import ImageData, ImageRequest, ImageResponse, ImageUsage

logger = logging.getLogger(__name__)


# ---------- 请求转换 ----------


def _map_pixel_size_to_agnes_style(size_str: str) -> tuple[str, Optional[str]]:
    """将传统像素尺寸（如 '1024x1024', '1920x1080'）自适应重映射为 Agnes 推荐的 size 档位和 ratio。"""
    if not size_str:
        return "1K", "1:1"

    size_upper = size_str.upper().strip()
    # 如果本来就是档位形式，直接保留，不自动推导 ratio（由外层 req.ratio 决定）
    if size_upper in ("1K", "2K", "3K", "4K"):
        return size_upper, None

    # 尝试解析 WxH
    if "X" in size_upper:
        parts = size_upper.split("X")
        if len(parts) == 2:
            try:
                width = int(parts[0].strip())
                height = int(parts[1].strip())
                if width > 0 and height > 0:
                    # 1) 计算像素面积，归类到最接近的档位
                    pixels = width * height
                    if pixels <= 1500000:  # <= 1.5 百万
                        mapped_size = "1K"
                    elif pixels <= 6000000:  # <= 6 百万
                        mapped_size = "2K"
                    elif pixels <= 12000000:  # <= 12 百万
                        mapped_size = "3K"
                    else:
                        mapped_size = "4K"

                    # 2) 计算宽高比，找到最接近的标准 ratio
                    ratio_val = width / height
                    # 标准 ratio 的比例值列表
                    standard_ratios = [
                        ("1:1", 1.0),
                        ("3:4", 3 / 4),
                        ("4:3", 4 / 3),
                        ("16:9", 16 / 9),
                        ("9:16", 9 / 16),
                        ("2:3", 2 / 3),
                        ("3:2", 3 / 2),
                        ("21:9", 21 / 9),
                    ]
                    # 寻找绝对差值最小的那个
                    best_ratio, _ = min(standard_ratios, key=lambda x: abs(ratio_val - x[1]))
                    return mapped_size, best_ratio
            except ValueError:
                pass

    # 无法解析或有异常时，回退原样返回，交由上游自带的标准化机制处理
    return size_str, None


def _openai_request_to_agnes_request(req: ImageRequest) -> AgnesImageRequest:
    """将 OpenAI 标准请求转换为 Agnes 上游请求。"""

    # 1) 优先继承客户端请求体中原生的 extra_body 参数（合并支持）
    orig_extra = req.extra_body or {}
    extra_body = AgnesExtraBody.model_validate(orig_extra)

    # 2) response_format: 从顶层移到 extra_body（顶层优先级更高）
    if req.response_format:
        extra_body.response_format = req.response_format

    # 3) image 数组: 映射到 extra_body.image（图生图，顶层优先级更高）
    if req.image:
        extra_body.image = req.image

    # 4) 构建顶层请求体（并引入尺寸自适应重映射）
    mapped_size, mapped_ratio = _map_pixel_size_to_agnes_style(req.size)

    agnes_req = AgnesImageRequest(
        model=req.model,
        prompt=req.prompt,
        size=mapped_size,
    )

    # 5) ratio: 顶层传入的 ratio 优先级高于重映射自动推导的 ratio
    if req.ratio:
        agnes_req.ratio = req.ratio
    elif mapped_ratio:
        agnes_req.ratio = mapped_ratio

    # Base64 输出：文生图使用顶层 return_base64，图生图使用 extra_body.response_format=b64_json
    has_image = bool(extra_body.image)
    if has_image:
        # 图生图 Base64：官方要求 extra_body.response_format=b64_json，顶层 return_base64 仅适用于文生图
        if req.return_base64 is True:
            extra_body.response_format = "b64_json"
    else:
        # 文生图 Base64：使用顶层 return_base64
        if req.return_base64 is not None:
            agnes_req.return_base64 = req.return_base64
        if req.response_format == "b64_json" or extra_body.response_format == "b64_json":
            agnes_req.return_base64 = True
            extra_body.response_format = None

    # 仅在 extra_body 有实际字段时才设置
    extra_dump = extra_body.model_dump(exclude_none=True)
    if extra_dump:
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

    # task_id 透传
    if agnes_resp.get("task_id"):
        resp.task_id = agnes_resp["task_id"]

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
        path="/v1/images/generations",
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

    # 检查缓存（仅非并行、非流式请求）
    cache_key = None
    if n == 1 and settings.enable_cache:
        cache_key = generate_image_cache_key(
            req.model, req.prompt or "",
            size=req.size,
            n=1,
            return_base64=req.return_base64,
            response_format=req.response_format,
            image=req.image,
        )
        cached_result = await request_cache.get(cache_key)
        if cached_result:
            logger.info("Cache HIT for image generation request")
            return cached_result

    from service.url_manager import get_url_manager
    base_url = get_url_manager().get_best_url()
    logger.info(
        f"Calling Agnes upstream | url={base_url} "
        f"model={req.model} prompt_len={len(req.prompt) if req.prompt else 0}"
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

    # 写入缓存
    if cache_key:
        response = ImageResponse(created=created, data=all_data)
        await request_cache.set(cache_key, response)
        logger.info(f"Cache SET: {cache_key[:16]}...")

    logger.info(
        f"Upstream calls complete | total_images={len(all_data)} "
        f"requests_sent={n} total_time={total_elapsed:.0f}ms"
    )

    return ImageResponse(created=created, data=all_data)