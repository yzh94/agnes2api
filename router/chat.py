"""OpenAI 兼容的 /v1/chat/completions 路由。"""

import logging
import traceback

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from models.openai_chat import ChatCompletionRequest
from service.auth import verify_api_key
from service.chat_transformer import UpstreamAPIError, call_agnes_chat, call_agnes_chat_stream
from service.errors import create_error_response
from service.model_guard import ensure_model_enabled

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/chat",
    tags=["Chat"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/completions", response_model=None)
async def create_chat_completion(request: Request):
    """OpenAI 兼容的聊天完成端点。"""
    try:
        body = await request.json()
        openai_req = ChatCompletionRequest.model_validate(body)

        logger.info(
            f"Chat completion request | model={openai_req.model} "
            f"messages={len(openai_req.messages)} stream={openai_req.stream}"
        )

        model_error = await ensure_model_enabled(openai_req.model)
        if model_error:
            return create_error_response(
                detail=model_error,
                status_code=400,
                error_type="invalid_request_error",
                default_code="model_not_allowed",
            )

        # 拦截原生的 base64 图像输入 (Agnes 视觉模型只支持公网 url)
        for msg in openai_req.messages:
            if isinstance(msg.get("content"), list):
                for part in msg["content"]:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        img_url_obj = part.get("image_url", {})
                        if isinstance(img_url_obj, dict):
                            img_url = img_url_obj.get("url", "")
                            if isinstance(img_url, str) and img_url.startswith("data:image/"):
                                return create_error_response(
                                    detail="Agnes model currently only supports public image URLs, not raw base64 data.",
                                    status_code=400,
                                    error_type="invalid_request_error",
                                    default_code="invalid_image_format"
                                )

        # 流式输出
        user_id = getattr(request.state, 'user_id', 0)
        if openai_req.stream:
            return StreamingResponse(
                call_agnes_chat_stream(openai_req, user_id=user_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # 非流式输出
        response = await call_agnes_chat(openai_req, user_id=user_id)
        logger.info(f"Chat completion OK | choices={len(response.get('choices', []))}")
        return response

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
        traceback.print_exc()
        return create_error_response(
            detail="Internal server error",
            status_code=500,
            error_type="server_error",
            default_code="internal_error",
        )
