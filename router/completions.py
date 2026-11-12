"""OpenAI Completions 兼容路由（/v1/completions）。

对接 New API 规范：
- 请求：model / prompt(string|array) / max_tokens / temperature / top_p / n / stream / stop / suffix / echo
- 响应：object="text_completion"，choices[].text

实现方式：将 prompt 包装为 user 消息，复用文本模型 Chat 接口，再转换为补全格式。
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
from service.model_guard import ensure_text_model

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1",
    tags=["Completions"],
    dependencies=[Depends(verify_api_key)],
)


def _prompt_to_messages(prompt: Any) -> list[dict[str, Any]]:
    """将 prompt（string 或 array）转换为 user 消息。"""
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    if isinstance(prompt, list):
        texts = [str(p) if not isinstance(p, dict) else p.get("text", "") for p in prompt]
        return [{"role": "user", "content": "\n".join(texts)}]
    raise ValueError("`prompt` must be a string or an array of strings.")


def _format_completion_id() -> str:
    return f"cmpl-{uuid.uuid4().hex[:24]}"


def _chat_to_completion_response(chat_resp: dict, model: str) -> dict:
    """将 Chat 响应转换为 Completions 响应。"""
    choices = []
    for i, choice in enumerate(chat_resp.get("choices", [])):
        message = choice.get("message", {})
        text = message.get("content") or ""
        if isinstance(text, list):
            parts = [p.get("text", "") for p in text if isinstance(p, dict) and p.get("type") == "text"]
            text = "\n".join(parts)
        choices.append({
            "text": text,
            "index": i,
            "finish_reason": choice.get("finish_reason", "stop"),
        })

    usage = chat_resp.get("usage", {})
    response = {
        "id": chat_resp.get("id", _format_completion_id()),
        "object": "text_completion",
        "created": chat_resp.get("created", int(time.time())),
        "model": model,
        "choices": choices,
    }
    if usage:
        response["usage"] = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }
    return response


def _chat_chunk_to_completion_chunk(
    chat_chunk: dict, completion_id: str, created: int, model: str
) -> dict:
    """将 Chat 流式 chunk 转换为 Completions 流式 chunk。"""
    choices = []
    for choice in chat_chunk.get("choices", []):
        delta = choice.get("delta", {})
        content = delta.get("content")
        text = content if content is not None else ""
        choices.append({
            "text": text,
            "index": choice.get("index", 0),
            "finish_reason": choice.get("finish_reason"),
        })
    return {
        "id": completion_id,
        "object": "text_completion",
        "created": created,
        "model": model,
        "choices": choices,
    }


@router.post("/completions", response_model=None)
async def create_completion(request: Request):
    """OpenAI 兼容的文本补全端点（流式 + 非流式）。"""
    try:
        body = await request.json()
        model = body.get("model", "agnes-2.5-flash")

        model_error = await ensure_text_model(model)
        if model_error:
            return create_error_response(
                detail=model_error,
                status_code=400,
                error_type="invalid_request_error",
                default_code="model_not_allowed",
            )

        try:
            messages = _prompt_to_messages(body.get("prompt"))
        except ValueError as e:
            return create_error_response(
                detail=str(e),
                status_code=400,
                error_type="invalid_request_error",
                default_code="invalid_request",
            )

        n = body.get("n", 1)
        if isinstance(n, int) and n > 1:
            return create_error_response(
                detail="Text completion via Agnes text model only supports n=1.",
                status_code=400,
                error_type="invalid_request_error",
                default_code="invalid_n",
            )

        stream = bool(body.get("stream", False))
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        for key in ("temperature", "top_p", "max_tokens", "max_completion_tokens", "user"):
            if body.get(key) is not None:
                kwargs[key] = body[key]

        openai_req = ChatCompletionRequest(**kwargs)
        user_id = getattr(request.state, 'user_id', 0)
        client_key_id = getattr(request.state, 'client_key_id', None)

        if stream:
            return _stream_completions(openai_req, user_id, client_key_id)

        response = await call_agnes_chat(openai_req, user_id=user_id, client_key_id=client_key_id, endpoint="/v1/completions")
        return _chat_to_completion_response(response, model)

    except UpstreamAPIError as e:
        logger.error(f"Completions upstream error | status={e.status_code} detail={e.detail}")
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="api_error",
            default_code="upstream_error",
        )
    except Exception:
        logger.exception("Unhandled internal server error in Completions")
        return create_error_response(
            detail="Internal server error",
            status_code=500,
            error_type="server_error",
            default_code="internal_error",
        )


def _stream_completions(openai_req: ChatCompletionRequest, user_id: int, client_key_id: int | None = None) -> StreamingResponse:
    """构建 Completions SSE 流式响应。"""
    completion_id = _format_completion_id()
    created = int(time.time())

    async def gen() -> AsyncGenerator[str, None]:
        async for chunk_str in call_agnes_chat_stream(openai_req, user_id=user_id, client_key_id=client_key_id, endpoint="/v1/completions"):
            try:
                chat_chunk = json.loads(chunk_str.replace("data: ", "").strip())
            except json.JSONDecodeError:
                continue
            if not chat_chunk.get("choices"):
                continue
            chunk = _chat_chunk_to_completion_chunk(chat_chunk, completion_id, created, openai_req.model)
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
