"""Gemini 兼容的聊天接口路由。

提供 Google Gemini 原生格式的文本对话接口：
- POST /v1beta/models/{model}:generateContent  (非流式)
- POST /v1beta/models/{model}:streamGenerateContent  (流式)

请求格式自动转换为 Agnes/OpenAI 兼容格式后转发，响应格式再转回 Gemini 格式。
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
    tags=["Gemini"],
    dependencies=[Depends(verify_api_key)],
)


# ============================================================
# Gemini 请求体解析
# ============================================================

def _parse_gemini_request(body: dict, model: str) -> ChatCompletionRequest:
    """将 Gemini 请求体转换为 OpenAI ChatCompletionRequest。"""
    messages = []
    for content_item in body.get("contents", []):
        role = content_item.get("role", "user")
        if role == "model":
            role = "assistant"
        parts = content_item.get("parts", [])
        text_parts = [p.get("text", "") for p in parts if p.get("text")]
        messages.append({"role": role, "content": "\n".join(text_parts)})

    generation_config = body.get("generationConfig", {})
    return ChatCompletionRequest(
        model=model,
        messages=messages,
        temperature=generation_config.get("temperature"),
        max_tokens=generation_config.get("maxOutputTokens"),
        top_p=generation_config.get("topP"),
        stream=False,
    )


# ============================================================
# Gemini 响应体转换
# ============================================================

def _agnes_to_gemini_response(agnes_resp: dict, model: str) -> dict:
    """将 Agnes/OpenAI 响应转换为 Gemini 格式。"""
    candidates = []
    for choice in agnes_resp.get("choices", []):
        message = choice.get("message", {})
        role = message.get("role", "assistant")
        text = message.get("content", "")
        candidates.append({
            "index": choice.get("index", 0),
            "content": {"role": role, "parts": [{"text": text}]},
            "finishReason": choice.get("finish_reason", "stop"),
        })

    usage = agnes_resp.get("usage", {})
    return {
        "candidates": candidates,
        "usageMetadata": {
            "promptTokenCount": usage.get("prompt_tokens", 0),
            "candidatesTokenCount": usage.get("completion_tokens", 0),
            "totalTokenCount": usage.get("total_tokens", 0),
        },
    }


def _openai_chunk_to_gemini_chunk(chunk: dict, model: str) -> dict:
    """将 OpenAI SSE chunk 转换为 Gemini SSE chunk。"""
    choices = chunk.get("choices", [])
    gemini_choices = []
    for choice in choices:
        delta = choice.get("delta", {})
        role = delta.get("role")
        content = delta.get("content")
        gemini_delta = {"role": role} if role else {}
        if content is not None:
            gemini_delta["parts"] = [{"text": content}]
        gemini_choices.append({
            "index": choice.get("index", 0),
            "delta": gemini_delta,
        })
        if choice.get("finish_reason"):
            gemini_choices[-1]["finishReason"] = choice["finish_reason"]

    return {
        "candidates": gemini_choices,
        "usageMetadata": chunk.get("usage", {}),
    }


# ============================================================
# 端点
# ============================================================

@router.post("/v1beta/models/{model}:generateContent")
async def generate_content(
    model: str,
    request: Request,
    db=None,
):
    """Gemini 非流式文本生成接口。"""
    try:
        body = await request.json()
        model_error = await ensure_model_enabled(model)
        if model_error:
            return create_error_response(
                detail=model_error,
                status_code=400,
                error_type="invalid_request_error",
                default_code="model_not_allowed",
            )
        openai_req = _parse_gemini_request(body, model)
        user_id = getattr(request.state, 'user_id', 0)

        response = await call_agnes_chat(openai_req, user_id=user_id)
        gemini_resp = _agnes_to_gemini_response(response, model)
        return gemini_resp

    except UpstreamAPIError as e:
        logger.error(f"Gemini upstream error | status={e.status_code}")
        return create_error_response(
            detail=e.detail, status_code=e.status_code,
            error_type="api_error", default_code="upstream_error",
        )
    except Exception:
        logger.exception("Unhandled error in Gemini generateContent")
        return create_error_response(
            detail="Internal server error", status_code=500,
            error_type="server_error", default_code="internal_error",
        )


@router.post("/v1beta/models/{model}:streamGenerateContent")
async def stream_generate_content(
    model: str,
    request: Request,
):
    """Gemini 流式文本生成接口。"""
    try:
        body = await request.json()
        model_error = await ensure_model_enabled(model)
        if model_error:
            return create_error_response(
                detail=model_error,
                status_code=400,
                error_type="invalid_request_error",
                default_code="model_not_allowed",
            )
        openai_req = _parse_gemini_request(body, model)
        openai_req.stream = True
        user_id = getattr(request.state, 'user_id', 0)

        async def gemini_stream_generator():
            # 发送第一个空 chunk（Gemini 规范要求）
            yield _format_gemini_chunk({"candidates": [], "usageMetadata": {}}, model)

            async for chunk_str in call_agnes_chat_stream(openai_req, user_id=user_id):
                try:
                    chunk_data = json.loads(chunk_str.replace("data: ", ""))
                    gemini_chunk = _openai_chunk_to_gemini_chunk(chunk_data, model)
                    yield _format_gemini_chunk(gemini_chunk, model)
                except json.JSONDecodeError:
                    continue

        return StreamingResponse(
            gemini_stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except UpstreamAPIError as e:
        logger.error(f"Gemini upstream error | status={e.status_code}")
        return create_error_response(
            detail=e.detail, status_code=e.status_code,
            error_type="api_error", default_code="upstream_error",
        )
    except Exception:
        logger.exception("Unhandled error in Gemini streamGenerateContent")
        return create_error_response(
            detail="Internal server error", status_code=500,
            error_type="server_error", default_code="internal_error",
        )


def _format_gemini_chunk(data: dict, model: str) -> str:
    """格式化为 Gemini SSE chunk。"""
    return f"data: {json.dumps(data)}\n\n"
