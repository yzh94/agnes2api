"""Gemini 兼容的聊天接口路由。

提供 Google Gemini 原生格式的文本对话接口：
- POST /v1beta/models/{model}:generateContent  (非流式)
- POST /v1beta/models/{model}:streamGenerateContent  (流式)

请求格式自动转换为 Agnes/OpenAI 兼容格式后转发，响应格式再转回 Gemini 格式。
支持 Gemini 图像生成（responseModalities 含 "IMAGE"）。
"""

import base64
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, NamedTuple

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from models.openai_chat import ChatCompletionRequest
from service.auth import verify_api_key
from service.chat_transformer import call_agnes_chat, call_agnes_chat_stream
from service.errors import UpstreamAPIError, create_error_response
from service.model_guard import ensure_model_enabled
from service.transformer import call_agnes_generate
from models.openai import ImageRequest

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Gemini"],
    dependencies=[Depends(verify_api_key)],
)


class GeminiRequestInfo(NamedTuple):
    """Gemini 请求解析结果。"""
    openai_req: ChatCompletionRequest
    is_image_gen: bool = False
    prompt: str = ""
    size: str = "1024x1024"
    ratio: str | None = None


# ============================================================
# Gemini 请求体解析
# ============================================================

def _parse_gemini_request(body: dict, model: str) -> GeminiRequestInfo:
    """将 Gemini 请求体转换为 OpenAI ChatCompletionRequest。

    支持多模态 parts：
    - text / image_url（公网 URL）-> 透传
    - inline_data / fileData（base64 / Google 云存储）-> 拒绝并给出明确提示，
      因为 Agnes 视觉模型只接受公开可访问的 URL。

    支持图像生成模式：当 generationConfig.responseModalities 包含 "IMAGE" 时，
    返回 is_image_gen=True，并提取 prompt、size、ratio 用于图像生成接口。

    Raises:
        ValueError: parts 含无法转发的输入类型时。
    """
    messages = []

    # system_instruction -> system 消息
    sys_instruction = body.get("system_instruction")
    if isinstance(sys_instruction, dict):
        sys_texts = [p.get("text", "") for p in sys_instruction.get("parts", []) if p.get("text")]
        if sys_texts:
            messages.append({"role": "system", "content": "\n".join(sys_texts)})

    # 检测图像生成模式
    generation_config = body.get("generationConfig", {})
    response_modalities = generation_config.get("responseModalities", [])
    image_gen_requested = any("IMAGE" in str(m).upper() for m in response_modalities)

    # 提取图像生成参数
    prompt = ""
    size = "1024x1024"
    ratio = None
    if image_gen_requested:
        # 从 contents 中提取文本 prompt
        for content_item in body.get("contents", []):
            role = content_item.get("role", "user")
            if role == "model":
                continue
            parts = content_item.get("parts", [])
            for p in parts:
                if isinstance(p, dict) and p.get("text"):
                    prompt = p["text"]
                    break
            if prompt:
                break

        # 从 imageConfig 或 generationConfig 提取尺寸参数
        image_config = generation_config.get("imageConfig", {})
        if image_config:
            # Gemini 的 imageConfig 格式
            pass  # 暂不支持 imageConfig 到 Agnes 的参数映射

    for content_item in body.get("contents", []):
        role = content_item.get("role", "user")
        if role == "model":
            role = "assistant"
        parts = content_item.get("parts", [])
        content_parts = []
        for p in parts:
            if not isinstance(p, dict):
                continue
            if p.get("inline_data") or p.get("fileData"):
                raise ValueError(
                    "Agnes model only supports public image URLs. "
                    "Gemini inline_data/fileData cannot be forwarded directly; "
                    "provide a public image URL part instead."
                )
            if p.get("text"):
                content_parts.append({"type": "text", "text": p["text"]})
                continue
            image_url = p.get("image_url")
            if isinstance(image_url, dict):
                image_url = image_url.get("url")
            if isinstance(image_url, str) and image_url:
                if image_url.startswith("data:image/"):
                    raise ValueError(
                        "Agnes model only supports public image URLs, not raw base64 data."
                    )
                content_parts.append({"type": "image_url", "image_url": {"url": image_url}})
        if not content_parts:
            continue
        # 纯文本单 part 保持字符串，其余为结构化 content 数组
        if len(content_parts) == 1 and content_parts[0]["type"] == "text":
            messages.append({"role": role, "content": content_parts[0]["text"]})
        else:
            messages.append({"role": role, "content": content_parts})

    # 如果未检测到 prompt，使用 messages 中的最后一条用户消息
    if not prompt and not image_gen_requested:
        for msg in reversed(messages):
            if msg["role"] == "user":
                content = msg["content"]
                if isinstance(content, str):
                    prompt = content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            prompt = part["text"]
                            break
                if prompt:
                    break

    return GeminiRequestInfo(
        openai_req=ChatCompletionRequest(
            model=model,
            messages=messages,
            temperature=generation_config.get("temperature"),
            max_tokens=generation_config.get("maxOutputTokens"),
            top_p=generation_config.get("topP"),
            stream=False,
        ),
        is_image_gen=image_gen_requested,
        prompt=prompt,
        size=size,
        ratio=ratio,
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


def _agnes_image_to_gemini_response(agnes_resp: dict, model: str) -> dict:
    """将 Agnes 图像生成响应转换为 Gemini 图像格式（含 inlineData）。

    Gemini 图像生成响应格式：
    {
      "candidates": [{
        "content": {
          "parts": [
            {"inlineData": {"mimeType": "image/png", "data": "base64..."}}
          ]
        }
      }]
    }
    """
    candidates = []
    for i, item in enumerate(agnes_resp.get("data", [])):
        b64_json = item.get("b64_json")
        if b64_json:
            # 从 base64 数据中提取 mime type（如果存在）
            mime_type = "image/png"
            if isinstance(b64_json, str) and b64_json.startswith("data:"):
                # data:image/png;base64,...
                parts = b64_json.split(",", 1)
                if len(parts) == 2 and ":" in parts[0]:
                    mime_type = parts[0].split(":")[1].split(";")[0]
                    b64_json = parts[1]
            candidates.append({
                "index": i,
                "content": {
                    "role": "model",
                    "parts": [{"inlineData": {"mimeType": mime_type, "data": b64_json}}],
                },
                "finishReason": "stop",
            })
        elif item.get("url"):
            # URL 格式不支持直接返回，提供错误提示
            candidates.append({
                "index": i,
                "content": {
                    "role": "model",
                    "parts": [{"text": f"Image generated at URL: {item['url']}"}],
                },
                "finishReason": "stop",
                "finishDetails": {"type": "tool_calls"},
            })

    return {
        "candidates": candidates,
        "model": model,
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
    """Gemini 非流式生成接口（支持文本和图像生成）。"""
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
        
        info = _parse_gemini_request(body, model)
        user_id = getattr(request.state, 'user_id', 0)
        client_key_id = getattr(request.state, 'client_key_id', None)

        # 路由分发：图像生成 vs 文本对话
        if info.is_image_gen:
            return await _handle_image_generation(info, model, user_id, client_key_id)
        else:
            return await _handle_text_generation(info, model, user_id, client_key_id)

    except ValueError as e:
        return create_error_response(
            detail=str(e),
            status_code=400,
            error_type="invalid_request_error",
            default_code="invalid_image_format",
        )
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


async def _handle_text_generation(info: GeminiRequestInfo, model: str, user_id: int, client_key_id: int | None = None) -> dict:
    """处理文本生成请求。"""
    response = await call_agnes_chat(info.openai_req, user_id=user_id, client_key_id=client_key_id, endpoint=f"/v1beta/models/{model}:generateContent")
    return _agnes_to_gemini_response(response, model)


async def _handle_image_generation(info: GeminiRequestInfo, model: str, user_id: int, client_key_id: int | None = None) -> dict:
    """处理图像生成请求，转换为 Gemini inlineData 格式。"""
    # 构建图像请求
    image_req = ImageRequest(
        model="agnes-image-2.1-flash",
        prompt=info.prompt,
        size=info.size,
        n=1,
    )
    
    logger.info(f"Gemini image generation | prompt={info.prompt[:50]}... size={info.size}")
    
    # 调用 Agnes 图像生成
    agnes_resp = await call_agnes_generate(image_req, user_id=user_id)
    
    # 转换为 Gemini 格式
    return _agnes_image_to_gemini_response(agnes_resp.model_dump(), model)


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
        client_key_id = getattr(request.state, 'client_key_id', None)

        async def gemini_stream_generator():
            # 发送第一个空 chunk（Gemini 规范要求）
            yield _format_gemini_chunk({"candidates": [], "usageMetadata": {}}, model)

            async for chunk_str in call_agnes_chat_stream(openai_req, user_id=user_id, client_key_id=client_key_id, endpoint=f"/v1beta/models/{model}:streamGenerateContent"):
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

    except ValueError as e:
        return create_error_response(
            detail=str(e),
            status_code=400,
            error_type="invalid_request_error",
            default_code="invalid_image_format",
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
