"""OpenAI Responses API 兼容路由（agnes-2.5-flash 新增能力）。

提供：
- POST /v1/responses    - 非流式（input -> messages -> Agnes Chat -> Responses 格式）
- POST /v1/responses (stream=true) - 流式（SSE，response.output_text.delta 事件）

对接官方文档：
- 请求：model / input(纯文本或结构化消息数组) / max_output_tokens
- 响应：output[]（reasoning + message，content[].output_text）+ usage
"""

import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from models.openai_chat import ChatCompletionRequest
from service.auth import verify_api_key
from service.chat_transformer import call_agnes_chat, call_agnes_chat_stream
from service.errors import UpstreamAPIError, create_error_response
from service.model_guard import ensure_model_enabled

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Responses"],
    dependencies=[Depends(verify_api_key)],
)


# ============================================================
# 请求体转换：input -> OpenAI messages
# ============================================================

def _part_to_openai(part: Any) -> tuple[dict[str, Any] | None, str | None]:
    """将 Responses 输入 part 转换为 OpenAI content part。

    Returns:
        (openai_part, error_message)；error_message 非空时表示无法转换。
    """
    if not isinstance(part, dict):
        return None, None

    ptype = part.get("type")
    if ptype in ("input_text", "output_text", "text"):
        return {"type": "text", "text": part.get("text", "")}, None
    if ptype == "input_image":
        image_url = part.get("image_url")
        url = image_url.get("url") if isinstance(image_url, dict) else image_url
        if isinstance(url, str) and url.startswith("data:image/"):
            return None, "Agnes model currently only supports public image URLs, not raw base64 data."
        if isinstance(url, str) and url:
            return {"type": "image_url", "image_url": {"url": url}}, None
        return None, "input_image requires a public image url."
    return None, None


def _input_to_messages(input_data: Any) -> tuple[list[dict[str, Any]], str | None]:
    """将 Responses 的 input（string 或数组）转换为 OpenAI messages。"""
    messages: list[dict[str, Any]] = []

    if isinstance(input_data, str):
        return [{"role": "user", "content": input_data}], None
    if not isinstance(input_data, list):
        return [], "`input` must be a string or an array."

    for item in input_data:
        if isinstance(item, str):
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue

        role = item.get("role", "user")
        if role == "model":
            role = "assistant"

        content = item.get("content", "")
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue
        if isinstance(content, list):
            parts: list[dict[str, Any]] = []
            for part in content:
                openai_part, err = _part_to_openai(part)
                if err:
                    return [], err
                if openai_part:
                    parts.append(openai_part)
            if parts:
                # 纯文本单 part 保持字符串，兼容上游
                if len(parts) == 1 and parts[0]["type"] == "text":
                    messages.append({"role": role, "content": parts[0]["text"]})
                else:
                    messages.append({"role": role, "content": parts})

    if not messages:
        return [], "`input` did not contain any valid messages."

    return messages, None


def _parse_responses_request(body: dict, model: str) -> tuple[ChatCompletionRequest | None, str | None]:
    """构建 ChatCompletionRequest，出错时返回错误消息。"""
    messages, err = _input_to_messages(body.get("input"))
    if err:
        return None, err

    max_output_tokens = body.get("max_output_tokens")
    stream = bool(body.get("stream", False))

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if isinstance(max_output_tokens, int) and max_output_tokens > 0:
        kwargs["max_tokens"] = max_output_tokens

    # 透传扩展参数
    for key in ("temperature", "top_p", "tools", "tool_choice", "chat_template_kwargs", "thinking", "user"):
        if key in body:
            kwargs[key] = body[key]

    try:
        return ChatCompletionRequest(**kwargs), None
    except Exception as e:
        return None, f"Invalid request: {e}"


# ============================================================
# 响应体转换：OpenAI Chat -> Responses API
# ============================================================

def _format_response_id() -> str:
    return f"resp_{uuid.uuid4().hex[:24]}"


def _chat_to_responses_response(openai_resp: dict, model: str) -> dict:
    """将 OpenAI Chat 响应转换为 Responses API 格式。"""
    output: list[dict[str, Any]] = []
    for choice in openai_resp.get("choices", []):
        message = choice.get("message", {})
        reasoning = message.get("reasoning_content")
        if reasoning:
            output.append({
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": reasoning}],
            })
        content = message.get("content")
        if content is not None:
            output.append({
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": content}],
            })

    usage = openai_resp.get("usage", {})
    return {
        "id": _format_response_id(),
        "object": "response",
        "created_at": openai_resp.get("created", int(time.time())),
        "status": "completed",
        "model": model,
        "output": output,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
        "error": None,
        "incomplete_details": None,
    }


# ============================================================
# 流式转换：OpenAI SSE chunk -> Responses SSE 事件
# ============================================================

def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _openai_chunk_to_responses_delta(chunk: dict, item_id: str) -> list[str]:
    """将 OpenAI SSE chunk 转换为 Responses 流式事件列表。"""
    events: list[str] = []
    for choice in chunk.get("choices", []):
        output_index = choice.get("index", 0)
        delta = choice.get("delta", {})

        reasoning = delta.get("reasoning_content")
        if reasoning:
            events.append(_sse("response.reasoning_summary_text.delta", {
                "type": "response.reasoning_summary_text.delta",
                "item_id": item_id,
                "output_index": output_index,
                "delta": reasoning,
            }))

        content = delta.get("content")
        if content is not None:
            events.append(_sse("response.output_text.delta", {
                "type": "response.output_text.delta",
                "item_id": item_id,
                "output_index": output_index,
                "delta": content,
            }))

        finish_reason = choice.get("finish_reason")
        if finish_reason:
            events.append(_sse("response.output_text.done", {
                "type": "response.output_text.done",
                "item_id": item_id,
                "output_index": output_index,
                "text": "",
            }))
    return events


async def _responses_stream_generator(openai_req: ChatCompletionRequest, user_id: int = 0, client_key_id: int | None = None) -> AsyncGenerator[str, None]:
    """将 Agnes/OpenAI 流转换为 Responses API SSE 事件流。"""
    response_id = _format_response_id()
    item_id = f"msg_{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    yield _sse("response.created", {
        "type": "response.created",
        "response": {
            "id": response_id,
            "object": "response",
            "created_at": created,
            "status": "in_progress",
            "model": openai_req.model,
            "output": [],
            "error": None,
            "incomplete_details": None,
        },
    })

    has_delta = False
    async for chunk_str in call_agnes_chat_stream(openai_req, user_id=user_id, client_key_id=client_key_id, endpoint="/v1/responses"):
        try:
            chunk = json.loads(chunk_str.replace("data: ", "").strip())
        except json.JSONDecodeError:
            continue
        events = _openai_chunk_to_responses_delta(chunk, item_id)
        if events:
            has_delta = True
        for ev in events:
            yield ev

    yield _sse("response.completed", {
        "type": "response.completed",
        "response": {
            "id": response_id,
            "object": "response",
            "created_at": created,
            "status": "completed" if has_delta else "in_progress",
            "model": openai_req.model,
            "output": [],
            "error": None,
            "incomplete_details": None,
        },
    })


# ============================================================
# 端点
# ============================================================

@router.post("/v1/responses", response_model=None)
async def create_response(request: Request):
    """OpenAI Responses API 端点（非流式 + 流式）。"""
    try:
        body = await request.json()
        model = body.get("model", "agnes-2.5-flash")

        model_error = await ensure_model_enabled(model)
        if model_error:
            return create_error_response(
                detail=model_error,
                status_code=400,
                error_type="invalid_request_error",
                default_code="model_not_allowed",
            )

        openai_req, err = _parse_responses_request(body, model)
        if err:
            return create_error_response(
                detail=err,
                status_code=400,
                error_type="invalid_request_error",
                default_code="invalid_request",
            )

        user_id = getattr(request.state, 'user_id', 0)
        client_key_id = getattr(request.state, 'client_key_id', None)

        if openai_req.stream:
            return StreamingResponse(
                _responses_stream_generator(openai_req, user_id=user_id, client_key_id=client_key_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        response = await call_agnes_chat(openai_req, user_id=user_id, client_key_id=client_key_id, endpoint="/v1/responses")
        return _chat_to_responses_response(response, model)

    except UpstreamAPIError as e:
        logger.error(f"Responses upstream error | status={e.status_code} detail={e.detail}")
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="api_error",
            default_code="upstream_error",
        )
    except Exception:
        logger.exception("Unhandled internal server error in Responses API")
        return create_error_response(
            detail="Internal server error",
            status_code=500,
            error_type="server_error",
            default_code="internal_error",
        )
