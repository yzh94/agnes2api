"""聊天请求 / 响应转换器：OpenAI Chat Completions API ⇄ Agnes Chat API。

对照 Agnes 2.0 Flash 文档验证：
- 请求参数：model, messages, temperature, top_p, max_tokens, stream, tools, tool_choice, chat_template_kwargs, thinking
- 响应格式：id, object, created, model, choices, usage

优化功能：
- 请求缓存（LRU + TTL）
- 详细性能日志
"""

import json
from service.upstream_client import request_upstream_with_retry
from service.errors import UpstreamAPIError
from service.llm_content_logger import get_llm_content_logger
from utils.http_client import get_http_client
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator, Any

import httpx

from config import settings
from service.redis_key_pool import get_key_pool_manager
from service.cache import request_cache, generate_text_cache_key
from service.key_stats import get_key_stats_manager, detect_model_type
from models.openai_chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChunkResponse,
    Choice,
    ChoiceDelta,
    Usage,
    DeltaChoice,
)

logger = logging.getLogger(__name__)




def _build_agnes_payload(req: ChatCompletionRequest) -> dict[str, Any]:
    """构建发送到 Agnes 的 JSON payload 字典。

    Agnes API 使用 OpenAI 兼容格式，直接透传请求参数。
    """
    
    # 1. 模型名称与 Thinking 模式处理
    # 为了解决 new-api 可能会过滤非标准字段的问题，支持通过模型名后缀触发
    is_thinking_model = False
    target_model = req.model
    if target_model.endswith("-thinking"):
        is_thinking_model = True
        # 根据文档，请求使用的模型必须是 agnes-2.5-flash
        target_model = target_model.replace("-thinking", "")
        
    payload: dict[str, Any] = {
        "model": target_model,
        "messages": req.messages,
    }

    # 添加可选参数（仅当值不为 None 时）
    if req.temperature is not None:
        payload["temperature"] = req.temperature
    if req.top_p is not None:
        payload["top_p"] = req.top_p
        
    # 2. 兼容 max_completion_tokens (OpenAI 新规范) 到 max_tokens
    if req.max_tokens is not None:
        payload["max_tokens"] = req.max_tokens
    elif req.max_completion_tokens is not None:
        payload["max_tokens"] = req.max_completion_tokens
        
    if req.stream:
        payload["stream"] = True
        
    # 3. 修复 tools 空数组被忽略的问题
    if req.tools is not None:
        payload["tools"] = req.tools
        
    if req.tool_choice is not None:
        payload["tool_choice"] = req.tool_choice

    # 处理 Thinking 模式
    # Agnes 上游通过 chat_template_kwargs.enable_thinking 开启思考。三种触发方式：
    #   1) 模型名 -thinking 后缀（OpenAI 兼容请求，绕过 new-api 字段过滤）
    #   2) 显式 chat_template_kwargs（透传，优先级最高；未显式指定 enable_thinking 时按需补齐）
    #   3) Anthropic 兼容 thinking 字段（thinking.type == "enabled" 时注入 enable_thinking）
    thinking_enabled = is_thinking_model or (
        isinstance(req.thinking, dict) and req.thinking.get("type") == "enabled"
    )

    if req.chat_template_kwargs:
        # 显式 chat_template_kwargs 优先；需开启思考且未显式指定 enable_thinking 时补齐
        chat_kwargs = {**req.chat_template_kwargs}
        if thinking_enabled and "enable_thinking" not in chat_kwargs:
            chat_kwargs["enable_thinking"] = True
        payload["chat_template_kwargs"] = chat_kwargs
    elif thinking_enabled:
        payload["chat_template_kwargs"] = {"enable_thinking": True}

    # Anthropic 兼容 thinking 字段透传（含 budget_tokens 等）
    if req.thinking:
        payload["thinking"] = req.thinking

    if req.user:
        payload["user"] = req.user

    return payload


def _format_response_id() -> str:
    """生成唯一的响应 ID。"""
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _format_chunk_id() -> str:
    """生成唯一的 chunk ID。"""
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _format_created() -> int:
    """生成当前时间戳。"""
    return int(time.time())


def _extract_content(message: dict[str, Any]) -> str | None:
    """从上游响应的 message 中提取 content 字段。"""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # 多模态响应，提取文本部分
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        return "\n".join(text_parts) if text_parts else None
    return str(content) if content else None

def _extract_reasoning_content(message: dict[str, Any]) -> str | None:
    """从上游响应的 message 中提取 reasoning_content 字段。"""
    content = message.get("reasoning_content")
    if isinstance(content, str):
        return content
    return str(content) if content else None


def _extract_tool_calls(message: dict[str, Any]) -> list[dict] | None:
    """从上游响应的 message 中提取 tool_calls 字段，并补充 index。"""
    tool_calls = message.get("tool_calls")
    if tool_calls and isinstance(tool_calls, list):
        # 为每个 tool_call 补充 index（OpenAI 规范要求）
        return [{**tc, "index": j} for j, tc in enumerate(tool_calls)]
    return None


def _deep_merge(base: dict, override: dict) -> None:
    """递归合并 dict：嵌套 dict 递归合并，嵌套 str 拼接，其他覆盖。"""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        elif k in base and isinstance(base[k], str) and isinstance(v, str):
            base[k] += v
        else:
            base[k] = v


def _response_to_openai_response(agnes_resp: dict[str, Any], model: str) -> dict[str, Any]:
    """将 Agnes 非流式响应转换为 OpenAI 兼容响应字典。"""
    choices_data = agnes_resp.get("choices", [])
    usage_data = agnes_resp.get("usage", {})

    choices = []
    for i, choice in enumerate(choices_data):
        message = choice.get("message", {})
        content = _extract_content(message)
        reasoning_content = _extract_reasoning_content(message)
        tool_calls = _extract_tool_calls(message)

        choice_obj = {
            "index": i,
            "message": {
                "role": message.get("role", "assistant"),
            },
            "finish_reason": choice.get("finish_reason", "stop"),
        }
        if content is not None:
            choice_obj["message"]["content"] = content
        if reasoning_content is not None:
            choice_obj["message"]["reasoning_content"] = reasoning_content
        if tool_calls:
            choice_obj["message"]["tool_calls"] = tool_calls
        choices.append(choice_obj)

    response = {
        "id": agnes_resp.get("id", _format_response_id()),
        "object": "chat.completion",
        "created": agnes_resp.get("created", _format_created()),
        "model": model,
        "choices": choices,
    }

    if usage_data:
        response["usage"] = {
            "prompt_tokens": usage_data.get("prompt_tokens", 0),
            "completion_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }

    return response


def _event_to_chunk(event: dict[str, Any], chunk_id: str, created: int, model: str) -> dict[str, Any]:
    """将 Agnes 流式事件转换为 OpenAI 兼容的 chunk 响应字典。"""
    choice_data = event.get("choices", [])
    choices = []

    for choice in choice_data:
        delta_data = choice.get("delta", {})
        role = delta_data.get("role")
        content = delta_data.get("content")
        finish_reason = choice.get("finish_reason")

        chunk = {
            "index": choice.get("index", 0),
            "delta": {},
        }

        if role:
            chunk["delta"]["role"] = role
        if content is not None:
            chunk["delta"]["content"] = content
        if finish_reason:
            chunk["finish_reason"] = finish_reason

        reasoning_content = delta_data.get("reasoning_content")
        if reasoning_content is not None:
            chunk["delta"]["reasoning_content"] = reasoning_content

        # 处理工具调用（补充 index，确保 OpenAI 兼容）
        tool_calls = delta_data.get("tool_calls")
        if tool_calls:
            for j, tc in enumerate(tool_calls):
                tc.setdefault("index", j)
            chunk["delta"]["tool_calls"] = tool_calls

        choices.append(chunk)

    result = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": choices,
    }

    # 检查是否是 usage 事件（如果合并在同一个 chunk 中，或者单独的 usage chunk 但是通过了前面的拦截）
    if "usage" in event:
        usage_data = event["usage"]
        result["usage"] = {
            "prompt_tokens": usage_data.get("prompt_tokens", 0),
            "completion_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }

    return result


async def call_agnes_chat(req: ChatCompletionRequest, user_id: int = 0, client_key_id: int | None = None, endpoint: str = "/v1/chat/completions") -> dict[str, Any]:
    """调用 Agnes Chat API，返回 OpenAI 兼容的非流式响应字典。

    优化功能：
    - 缓存支持：相同请求直接返回缓存结果
    - 详细性能日志：记录各阶段耗时
    """
    # 检查是否需要缓存
    cache_key = None
    if not req.stream and settings.enable_cache:
        cache_key = generate_text_cache_key(
            req.model, req.messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        cached_result = await request_cache.get(cache_key)
        if cached_result:
            logger.info("Cache HIT for text chat request")
            return cached_result

    payload = _build_agnes_payload(req)
    # 检测模型类型
    model_type = detect_model_type(req.model)

    t_total_start = time.monotonic()
    logger.info("=" * 60)
    logger.info("CHAT REQUEST START [非流式]")
    logger.info(f"  Model: {req.model}")
    logger.info(f"  Messages: {len(req.messages)}")
    logger.info(f"  Stream: {req.stream}")
    logger.info(f"  Temperature: {req.temperature}")
    logger.info(f"  Max Tokens: {req.max_tokens}")
    logger.info(f"  Tools: {len(req.tools) if req.tools else 0}")
    logger.info(f"  Thinking: {req.thinking}")
    logger.info(f"  Cache Key: {cache_key[:16] + '...' if cache_key else 'N/A'}")
    logger.info("=" * 60)

    # 使用统一的自动换 Key/重试客户端：失败自动换下一把 Key 重试，
    # 成功时返回 (response, 实际成功的那把 full_key)。
    # 关键：full_key 是真正请求成功的那把 Key，统计与响应都跟随它，保证
    #       “请求成功的 Key” 与 “响应使用的 Key” 一致。
    # 失败统计、401 自动禁用、降级判定均由其内部完成，此处无需重复记录。
    t_http_start = time.monotonic()
    http_resp, full_key = await request_upstream_with_retry(
        method="POST",
        path="/v1/chat/completions",
        model_type=model_type,
        payload=payload,
        max_retries=1,
        user_id=user_id,
    )
    http_elapsed = (time.monotonic() - t_http_start) * 1000
    logger.info(f"[{http_elapsed:.0f}ms] Upstream HTTP response received: status={http_resp.status_code} key={full_key[:8]}...")

    t_parse_start = time.monotonic()
    agnes_json = http_resp.json()
    parse_elapsed = (time.monotonic() - t_parse_start) * 1000
    logger.info(f"[{parse_elapsed:.0f}ms] Response JSON parsed")

    # 记录响应摘要
    choices_count = len(agnes_json.get("choices", []))
    usage = agnes_json.get("usage", {})
    logger.info(f"Response summary: choices={choices_count}, "
                f"prompt_tokens={usage.get('prompt_tokens')}, "
                f"completion_tokens={usage.get('completion_tokens')}")

    t_convert_start = time.monotonic()
    result = _response_to_openai_response(agnes_json, req.model)
    convert_elapsed = (time.monotonic() - t_convert_start) * 1000
    logger.info(f"[{convert_elapsed:.0f}ms] Response converted to OpenAI format")

    # 写入缓存
    if cache_key:
        await request_cache.set(cache_key, result)
        logger.info(f"Cache SET: {cache_key[:16]}...")

    total_elapsed = (time.monotonic() - t_total_start) * 1000
    logger.info(f"[{total_elapsed:.0f}ms] CHAT REQUEST END [非流式]")
    logger.info("=" * 60)

    # 写入 LLM 内容日志（异步，不阻塞返回）
    get_llm_content_logger().write_log({
        "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "request_id": result.get("id"),
        "user_id": user_id,
        "client_key_id": client_key_id,
        "endpoint": endpoint,
        "stream": False,
        "model": req.model,
        "input": payload,
        "output": result,
        "duration_ms": total_elapsed,
        "first_chunk_ms": None,
        "upstream_key_prefix": full_key[:8] if full_key else None,
    })

    return result


async def call_agnes_chat_stream(req: ChatCompletionRequest, user_id: int = 0, client_key_id: int | None = None, endpoint: str = "/v1/chat/completions") -> AsyncGenerator[str, None]:
    """调用 Agnes Chat API 流式接口，生成 OpenAI 兼容的 SSE 流式响应。

    优化说明：
    - 使用 httpx 的 stream 模式，实现真正的实时转发
    - 上游返回的第一个 chunk 到达后，立即开始向客户端发送
    - 不等待全部完成，减少内存占用和延迟

    Key 一致性策略：
    - 连接阶段（建立流式连接、收到首个状态码之前）失败时，自动换下一把 Key 重试
    - 一旦连接成功（HTTP 2xx），立即锁定该 Key，后续整个响应流都使用这把 Key，
      不再中途换 Key（避免响应内容错乱），保证"请求成功的 Key"与"响应使用的 Key"一致
    """
    from service.key_disable import check_and_disable_key_on_401

    payload = _build_agnes_payload(req)
    key_pool = get_key_pool_manager()
    stats_manager = get_key_stats_manager()
    http_client = get_http_client()
    model_type = detect_model_type(req.model)

    chunk_id = _format_chunk_id()
    created = _format_created()

    t_total_start = time.monotonic()
    logger.info("=" * 60)
    logger.info("CHAT STREAM REQUEST START [流式]")
    logger.info(f"  Model: {req.model}")
    logger.info(f"  Messages: {len(req.messages)}")
    logger.info(f"  Max Tokens: {req.max_tokens}")
    logger.info("=" * 60)

    # ---------- 建立流式连接 + 消费响应（失败换 Key 重试，空流也可重试） ----------
    max_retries = 2  # 最多尝试 3 把 Key（首次 + 2 次重试）
    http_resp = None
    used_key = None
    last_exception = None
    tried_keys: set[str] = set()  # 本次请求已失败的 Key，重试时排除
    stream_ok = False  # 请求级最终结果（用户视角：开始收到真实内容即成功）
    last_key: str | None = None  # 终局归属 Key：成功为实际成功的 Key，失败为最后尝试的 Key
    from service.url_manager import get_url_manager
    url_manager = get_url_manager()

    try:
        for attempt in range(max_retries + 1):
            # ---------- 阶段1：建立流式连接 ----------
            api_key = await key_pool.get_next_key(exclude=tried_keys)
            if not api_key:
                # 没有可用 Key：若之前已有失败异常则抛出，否则直接 503
                raise last_exception if last_exception else UpstreamAPIError(
                    status_code=503,
                    detail={"message": "No available API keys in pool"},
                )
            full_key = key_pool._get_full_key(api_key)
            if not full_key:
                raise UpstreamAPIError(
                    status_code=503,
                    detail={"message": f"Cannot find full key for {api_key}"},
                )
            tried_keys.add(full_key)
            last_key = full_key

            masked_key = key_pool._compute_key_prefix(full_key)
            logger.info(f"Stream connect | attempt={attempt + 1}/{max_retries + 1} key={masked_key}")

            base_url = url_manager.get_best_url()
            url = f"{base_url}/v1/chat/completions"

            t_http_start = time.monotonic()
            try:
                request = http_client.build_request(
                    "POST",
                    url,
                    headers={
                        "Authorization": f"Bearer {full_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                http_resp = await http_client.send(request, stream=True)
                if http_resp.status_code >= 500:
                    url_manager.record_result(base_url, False)
                else:
                    url_manager.record_result(base_url, True)
            except Exception as e:
                # 连接阶段异常（网络超时、连接被拒等）：节点级故障，不累计 Key 连续失败
                url_manager.record_result(base_url, False)
                logger.error(f"Stream connect error (attempt {attempt + 1}): {e}")
                await key_pool.record_failure(full_key, reason="network", degradable=False)
                last_exception = UpstreamAPIError(status_code=502, detail=f"上游网关错误: {str(e)}")
                http_resp = None
                continue

            # 连接已建立，检查状态码（此时尚未消费 body）
            if http_resp.status_code >= 400:
                status_code = http_resp.status_code
                http_elapsed = (time.monotonic() - t_http_start) * 1000
                logger.error(f"[{http_elapsed:.0f}ms] Stream upstream error: status={status_code} key={masked_key}")
                try:
                    error_body = await http_resp.aread()
                except Exception:
                    error_body = b""
                finally:
                    await http_resp.aclose()
                http_resp = None

                err_detail: Any = error_body.decode()
                try:
                    err_json = json.loads(err_detail)
                    if isinstance(err_json, dict):
                        err_detail = err_json
                except json.JSONDecodeError:
                    pass

                # 客户端参数错误（400/404/422 等，排除 401/403/408/429）：
                # 与 Key 健康无关，不记 Key 失败、不换 Key 重试，直接抛出
                is_client_fault = 400 <= status_code < 500 and status_code not in (401, 403, 408, 429)
                if is_client_fault:
                    raise UpstreamAPIError(status_code=status_code, detail=err_detail)

                # Key 可归责失败：分类记录（429 立即降级 / 401·403 鉴权 / 408·5xx 服务端）
                if status_code == 429:
                    fail_reason = "rate_limit"
                elif status_code in (401, 403):
                    fail_reason = "auth"
                else:
                    fail_reason = "server"
                await check_and_disable_key_on_401(
                    full_key, status_code,
                    err_detail if isinstance(err_detail, dict) else {"error": {"message": err_detail}},
                )
                await key_pool.record_failure(full_key, reason=fail_reason)
                last_exception = UpstreamAPIError(status_code=status_code, detail=err_detail)
                continue

            # 连接成功：锁定这把 Key，整个响应流都使用它，不再换 Key
            used_key = full_key
            http_elapsed = (time.monotonic() - t_http_start) * 1000
            logger.info(f"[{http_elapsed:.0f}ms] Stream connection established, locked key={masked_key}")

            # ---------- 阶段2：消费流式响应（锁定 used_key，不再换 Key） ----------
            chunk_count = 0
            first_chunk_time = None
            has_usage = False
            accumulated_usage: dict[str, int] = {}  # 累积上游返回的真实 usage 数据

            # 累积完整输出内容用于日志记录
            accumulated_content = ""
            accumulated_reasoning = ""
            accumulated_tool_calls: list[dict] = []
            finish_reason: str | None = None

            async for line in http_resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:].strip()

                    # 流结束标记
                    if data_str == "[DONE]":
                        total_elapsed = (time.monotonic() - t_total_start) * 1000
                        logger.info(f"[{total_elapsed:.0f}ms] Stream completed, total chunks: {chunk_count}")
                        logger.info("CHAT STREAM REQUEST END [流式]")
                        logger.info("=" * 60)
                        break

                    try:
                        event = json.loads(data_str)

                        # 检查是否是 usage 事件
                        if "usage" in event:
                            usage_data = event["usage"]
                            # 累积真实的 usage 数据
                            accumulated_usage["prompt_tokens"] = usage_data.get("prompt_tokens", 0)
                            accumulated_usage["completion_tokens"] = usage_data.get("completion_tokens", 0)
                            accumulated_usage["total_tokens"] = usage_data.get("total_tokens", 0)
                            logger.info(f"Usage: prompt_tokens={accumulated_usage.get('prompt_tokens')}, "
                                        f"completion_tokens={accumulated_usage.get('completion_tokens')}, "
                                        f"total_tokens={accumulated_usage.get('total_tokens')}")
                            has_usage = True

                            # 注意：如果当前 chunk 同时包含 choices（即合并返回的情况），不能 continue，必须继续处理
                            if "choices" not in event or not event["choices"]:
                                continue

                        # 转换为 OpenAI chunk 格式
                        chunk = _event_to_chunk(event, chunk_id, created, req.model)
                        chunk_count += 1

                        # 累积流式输出内容用于日志记录
                        for choice in event.get("choices", []):
                            delta = choice.get("delta", {})
                            content = delta.get("content")
                            if content is not None:
                                accumulated_content += content
                            reasoning = delta.get("reasoning_content")
                            if reasoning is not None:
                                accumulated_reasoning += reasoning
                            tool_calls = delta.get("tool_calls")
                            if tool_calls:
                                for tc in tool_calls:
                                    tc_idx = tc.get("index", 0)
                                    while len(accumulated_tool_calls) <= tc_idx:
                                        accumulated_tool_calls.append({})
                                    # 深度合并：dict 递归合并（嵌套 str 拼接），其他覆盖
                                    acc_tc = accumulated_tool_calls[tc_idx]
                                    for k, v in tc.items():
                                        if k in acc_tc:
                                            if isinstance(acc_tc[k], dict) and isinstance(v, dict):
                                                _deep_merge(acc_tc[k], v)
                                            elif isinstance(acc_tc[k], str) and isinstance(v, str):
                                                acc_tc[k] += v
                                            else:
                                                acc_tc[k] = v
                                        else:
                                            acc_tc[k] = v
                            fr = choice.get("finish_reason")
                            if fr:
                                finish_reason = fr

                        # 记录首 chunk 时间
                        if chunk_count == 1:
                            first_chunk_time = (time.monotonic() - t_total_start) * 1000
                            logger.info(f"[{first_chunk_time:.0f}ms] First chunk received (TTFB)")
                            stream_ok = True  # 用户已开始收到真实内容

                        # 实时 yield 给客户端
                        yield f"data: {json.dumps(chunk)}\n\n"

                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse SSE event: {e}, data: {data_str[:100]}")

            # 流结束但未遇到 [DONE]
            if chunk_count > 0 and not has_usage:
                logger.warning(f"Stream ended without usage data, total chunks: {chunk_count}")

            # 发送最终的 usage chunk（如果请求了且累积了 usage 数据）
            if has_usage and accumulated_usage.get("prompt_tokens", 0) > 0:
                final_usage_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": req.model,
                    "choices": [],
                    "usage": accumulated_usage,
                }
                yield f"data: {json.dumps(final_usage_chunk)}\n\n"

            if chunk_count == 0:
                # 空流：记 zero_chunk 失败，允许换 Key 重试（尚未向客户端输出任何内容）
                await http_resp.aclose()
                http_resp = None
                await key_pool.record_failure(used_key, reason="zero_chunk")
                total_elapsed = (time.monotonic() - t_total_start) * 1000
                logger.warning(f"[{total_elapsed:.0f}ms] Stream ended with no chunks received (attempt {attempt + 1})")
                last_exception = UpstreamAPIError(status_code=502, detail={"message": "上游返回空流"})
                used_key = None
                if attempt < max_retries:
                    continue
                # 所有重试均返回空流：结束流（保持既有行为，客户端看到空流结束）
                return

            # 流式请求成功完成，记录成功
            await key_pool.record_success(used_key)
            total_elapsed = (time.monotonic() - t_total_start) * 1000
            logger.info(f"[{total_elapsed:.0f}ms] Stream request completed successfully")

            # 写入 LLM 内容日志（异步，不阻塞主流程）
            output_message: dict[str, Any] = {"role": "assistant"}
            if accumulated_content:
                output_message["content"] = accumulated_content
            if accumulated_reasoning:
                output_message["reasoning_content"] = accumulated_reasoning
            if accumulated_tool_calls:
                output_message["tool_calls"] = accumulated_tool_calls
            output_message["finish_reason"] = finish_reason or "stop"

            output_obj: dict[str, Any] = {
                "id": chunk_id,
                "object": "chat.completion",
                "created": created,
                "model": req.model,
                "choices": [{"index": 0, "message": output_message}],
            }
            if accumulated_usage:
                output_obj["usage"] = accumulated_usage

            get_llm_content_logger().write_log({
                "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                "request_id": chunk_id,
                "user_id": user_id,
                "client_key_id": client_key_id,
                "endpoint": endpoint,
                "stream": True,
                "model": req.model,
                "input": payload,
                "output": output_obj,
                "duration_ms": total_elapsed,
                "first_chunk_ms": first_chunk_time,
                "upstream_key_prefix": used_key[:8] if used_key else None,
            })
            return

        # 所有重试均在连接阶段失败
        raise last_exception if last_exception else UpstreamAPIError(status_code=502, detail="上游连接失败")
    finally:
        # 终局一次性记账：整个请求（含内部重试）只按最终结果记一次（用户视角成功率）。
        # 中间尝试不产生成功率计数；Key Pool 的 record_success/record_failure 已在
        # 各尝试点独立承担 Key 健康观测。last_key 为 None（未尝试任何 Key）时只记请求级。
        try:
            stats_manager.record_final_outcome(model_type, stream_ok, key=last_key, user_id=user_id)
        except Exception:
            pass  # 请求级统计失败不影响主流程
        # 确保流式响应被关闭，释放连接
        if http_resp is not None:
            await http_resp.aclose()

