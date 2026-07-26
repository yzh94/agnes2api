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
from utils.http_client import get_http_client
import logging
import time
import uuid
from typing import AsyncGenerator, Any

import httpx

from config import settings
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
        # 根据文档，请求使用的模型必须是 agnes-2.0-flash
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
    # 如果请求显式带了该参数则透传；或者通过模型名后缀自动注入（针对 OpenAI 兼容请求）
    if req.chat_template_kwargs:
        payload["chat_template_kwargs"] = req.chat_template_kwargs
    elif is_thinking_model:
        payload["chat_template_kwargs"] = {"enable_thinking": True}
        
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


async def call_agnes_chat(req: ChatCompletionRequest, user_id: int = 0) -> dict[str, Any]:
    """调用 Agnes Chat API，返回 OpenAI 兼容的非流式响应字典。"""
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
    logger.info("=" * 60)

    # 使用统一的自动换 Key/重试客户端：失败自动换下一把 Key 重试，
    # 成功时返回 (response, 实际成功的那把 full_key)。
    # 关键：full_key 是真正请求成功的那把 Key，统计与响应都跟随它，保证
    #       “请求成功的 Key” 与 “响应使用的 Key” 一致。
    # 失败统计、401 自动禁用、降级判定均由其内部完成，此处无需重复记录。
    t_http_start = time.monotonic()
    http_resp, full_key = await request_upstream_with_retry(
        method="POST",
        url_template=f"{settings.agnes_base_url}/v1/chat/completions",
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

    total_elapsed = (time.monotonic() - t_total_start) * 1000
    logger.info(f"[{total_elapsed:.0f}ms] CHAT REQUEST END [非流式]")
    logger.info("=" * 60)

    return result


async def call_agnes_chat_stream(req: ChatCompletionRequest, user_id: int = 0) -> AsyncGenerator[str, None]:
    """调用 Agnes Chat API 流式接口，生成 OpenAI 兼容的 SSE 流式响应。

    优化说明：
    - 使用 httpx 的 stream 模式，实现真正的实时转发
    - 上游返回的第一个 chunk 到达后，立即开始向客户端发送
    - 不等待全部完成，减少内存占用和延迟

    Key 一致性策略：
    - 连接阶段（建立流式连接、收到首个状态码之前）失败时，自动换下一把 Key 重试
    - 一旦连接成功（HTTP 2xx），立即锁定该 Key，后续整个响应流都使用这把 Key，
      不再中途换 Key（避免响应内容错乱），保证“请求成功的 Key”与“响应使用的 Key”一致
    """
    from service.key_disable import check_and_disable_key_on_401
    from service.simple_key_pool import get_key_pool_manager as _get_key_pool

    payload = _build_agnes_payload(req)
    key_pool = _get_key_pool()
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

    # ---------- 阶段1：建立流式连接（失败换 Key 重试） ----------
    max_retries = 1  # 最多尝试 2 把 Key（首次 + 1 次重试）
    url = f"{settings.agnes_base_url}/v1/chat/completions"
    http_resp = None
    used_key = None
    last_exception = None

    for attempt in range(max_retries + 1):
        api_key = await key_pool.get_next_key()
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

        masked_key = key_pool._compute_key_prefix(full_key)
        logger.info(f"Stream connect | attempt={attempt + 1}/{max_retries + 1} key={masked_key}")

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
        except Exception as e:
            # 连接阶段异常（网络超时、连接被拒等）：记录失败，换 Key 重试
            logger.error(f"Stream connect error (attempt {attempt + 1}): {e}")
            await key_pool.record_failure(full_key)
            stats_manager.record_request(full_key, model_type, False, user_id=user_id)
            last_exception = UpstreamAPIError(status_code=502, detail=f"上游网关错误: {str(e)}")
            http_resp = None
            continue
        finally:
            # 确保 build_request 阶段的异常不会泄漏连接资源
            pass

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

            err_detail: Any = error_body.decode()
            try:
                err_json = json.loads(err_detail)
                if isinstance(err_json, dict):
                    err_detail = err_json
            except json.JSONDecodeError:
                pass

            await check_and_disable_key_on_401(
                full_key, status_code,
                err_detail if isinstance(err_detail, dict) else {"error": {"message": err_detail}},
            )
            await key_pool.record_failure(full_key)
            stats_manager.record_request(full_key, model_type, False, user_id=user_id)
            last_exception = UpstreamAPIError(status_code=status_code, detail=err_detail)
            http_resp = None
            continue

        # 连接成功：锁定这把 Key，整个响应流都使用它，不再换 Key
        used_key = full_key
        http_elapsed = (time.monotonic() - t_http_start) * 1000
        logger.info(f"[{http_elapsed:.0f}ms] Stream connection established, locked key={masked_key}")
        break

    if http_resp is None or used_key is None:
        # 所有重试均失败
        raise last_exception if last_exception else UpstreamAPIError(status_code=502, detail="上游连接失败")

    # ---------- 阶段2：消费流式响应（锁定 used_key，不再换 Key） ----------
    chunk_count = 0
    first_chunk_time = None
    has_usage = False
    accumulated_usage: dict[str, int] = {}  # 累积上游返回的真实 usage 数据

    try:
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

                    # 记录首 chunk 时间
                    if chunk_count == 1:
                        first_chunk_time = (time.monotonic() - t_total_start) * 1000
                        logger.info(f"[{first_chunk_time:.0f}ms] First chunk received (TTFB)")

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

        # 流结束统计：跟随实际成功的那把 Key
        if chunk_count == 0:
            # 流结束但没有收到任何 chunk，记录失败
            await key_pool.record_failure(used_key)
            stats_manager.record_request(used_key, model_type, False, user_id=user_id)
            total_elapsed = (time.monotonic() - t_total_start) * 1000
            logger.warning(f"[{total_elapsed:.0f}ms] Stream ended with no chunks received")
        else:
            # 流式请求成功完成，记录成功
            await key_pool.record_success(used_key)
            stats_manager.record_request(used_key, model_type, True, user_id=user_id)
            total_elapsed = (time.monotonic() - t_total_start) * 1000
            logger.info(f"[{total_elapsed:.0f}ms] Stream request completed successfully")
    finally:
        # 确保流式响应被关闭，释放连接
        await http_resp.aclose()

