"""视频模型路由：OpenAI Sora 兼容 + New API 通用格式的视频生成 API。

提供以下端点：
- POST /v1/videos                 - 创建视频任务（Sora 主路径，返回 Video 对象）
- GET /v1/videos/{id}             - 查询视频任务状态（Sora 格式）
- GET /v1/videos/{id}/content     - 流式回传视频内容（video/mp4，支持 Range）
- POST /v1/video/generations      - 创建视频任务（New API 通用格式，返回 {task_id, status}）
- GET /v1/video/generations/{id}  - 查询视频任务状态（New API 格式：task_id/status/url/format/metadata/error）
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from models.video import VideoRequest
from router.proxy import stream_proxy
from service.auth import verify_api_key
from service.errors import create_error_response
from service.model_guard import ensure_model_enabled
from service.video import (
    TaskNotFoundError,
    UpstreamAPIError,
    VideoService,
    get_video_service,
)

logger = logging.getLogger(__name__)

# 主路由器：带 /v1/video prefix，用于 OpenAI 兼容格式（兼容别名）
router = APIRouter(
    prefix="/v1/video",
    tags=["Video"],
    dependencies=[Depends(verify_api_key)],
)

# 独立路由器：不带 prefix，用于 /v1/videos（Sora 主路径）
router_v1_videos = APIRouter(
    tags=["Video"],
    dependencies=[Depends(verify_api_key)],
)


async def _parse_video_body(request: Request) -> dict[str, Any] | Any:
    """解析请求体（JSON 或 multipart），返回 body dict 或 create_error_response 错误响应。"""
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        body: dict[str, Any] = {}
        for k, v in form.items():
            from starlette.datastructures import UploadFile

            if isinstance(v, UploadFile):
                # 上游 Agnes 图生视频仅支持公网 URL，不接受文件上传
                return create_error_response(
                    detail="File upload not supported for video input; provide an image URL via 'input' or 'image' field.",
                    status_code=400,
                    error_type="invalid_request_error",
                    default_code="unsupported_file_upload",
                )
            body[k] = v

        # 兼容表单字段：seconds -> duration, size -> width/height
        if "seconds" in body and "duration" not in body:
            try:
                body["duration"] = float(str(body["seconds"]))
            except ValueError:
                pass
        if "size" in body and "width" not in body and "height" not in body:
            try:
                parts = str(body["size"]).split("x")
                if len(parts) == 2:
                    body["width"] = int(parts[0])
                    body["height"] = int(parts[1])
            except Exception:
                pass
        return body

    raw_body = await request.body()
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return create_error_response(
            detail=f"Invalid JSON payload: {raw_body.decode('utf-8', errors='replace')}",
            status_code=400,
            error_type="invalid_request_error",
            default_code="invalid_json",
        )


async def _create_video_core(
    request: Request,
    video_service: VideoService,
) -> Any:
    """共享的视频创建逻辑。返回 Video 对象或错误响应（JSONResponse）。"""
    body = await _parse_video_body(request)
    # _parse_video_body 可能返回错误响应（JSONResponse）
    if hasattr(body, "status_code"):
        return body

    video_req = VideoRequest(**body)

    logger.info(
        f"Video generation | model={video_req.model} "
        f"prompt_len={len(video_req.prompt) if video_req.prompt else 0} "
        f"size={video_req.size} seconds={video_req.seconds} "
        f"has_input={'yes' if video_req.input else 'no'}"
    )

    model_error = await ensure_model_enabled(video_req.model)
    if model_error:
        return create_error_response(
            detail=model_error,
            status_code=400,
            error_type="invalid_request_error",
            default_code="model_not_allowed",
        )

    user_id = getattr(request.state, 'user_id', 0)
    return await video_service.create_video_task(video_req, user_id=user_id)


# ---------- 创建视频任务 ----------
@router_v1_videos.post(
    "/v1/videos",
    response_model=None,
    summary="创建视频任务",
    description="提交视频生成任务，支持文生视频和图生视频。返回 Sora Video 对象。",
)
async def create_video_generation(
    request: Request,
    video_service: VideoService = Depends(get_video_service),
):
    """OpenAI Sora 兼容的视频生成端点。返回 Video 对象（object="video"）。"""
    try:
        video = await _create_video_core(request, video_service)
        if hasattr(video, "status_code"):
            return video
        logger.info(f"Video generation created | id={video.id} status={video.status}")
        return video.model_dump(exclude_none=True)

    except UpstreamAPIError as e:
        logger.error(f"Video upstream API error | status={e.status_code} detail={e.detail}")
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="api_error",
            default_code="upstream_error",
        )
    except TaskNotFoundError as e:
        logger.error(f"Task not found | detail={e.detail}")
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="not_found",
            default_code="task_not_found",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled internal server error")
        return create_error_response(
            detail="Internal server error",
            status_code=500,
            error_type="server_error",
            default_code="internal_error",
        )


@router.post(
    "/generations",
    response_model=None,
    summary="创建视频任务（New API 通用格式）",
    description="提交视频生成任务。返回 {task_id, status}，任务结果通过 GET /v1/video/generations/{task_id} 查询。",
)
async def create_video_generation_newapi(
    request: Request,
    video_service: VideoService = Depends(get_video_service),
):
    """New API 通用格式的视频创建端点。返回 {task_id, status}。"""
    try:
        video = await _create_video_core(request, video_service)
        if hasattr(video, "status_code"):
            return video
        logger.info(f"Video generation created | id={video.id} status={video.status}")
        return {"task_id": video.id, "status": video.status}

    except UpstreamAPIError as e:
        logger.error(f"Video upstream API error | status={e.status_code} detail={e.detail}")
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="api_error",
            default_code="upstream_error",
        )
    except TaskNotFoundError as e:
        logger.error(f"Task not found | detail={e.detail}")
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="not_found",
            default_code="task_not_found",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled internal server error")
        return create_error_response(
            detail="Internal server error",
            status_code=500,
            error_type="server_error",
            default_code="internal_error",
        )


# ---------- 查询视频任务状态 ----------
@router_v1_videos.get(
    "/v1/videos/{task_id}",
    response_model=None,
    summary="查询视频任务状态",
)
async def get_video_generation(
    task_id: str,
    video_service: VideoService = Depends(get_video_service),
):
    """查询视频任务状态，返回 Sora Video 对象（不含 url；视频内容通过 /content 获取）。"""
    try:
        logger.info(f"Video status query | task_id={task_id}")
        video = await video_service.get_video_status(task_id)
        logger.info(f"Video status | task_id={task_id} status={video.status}")
        return video.model_dump(exclude_none=True)

    except UpstreamAPIError as e:
        logger.error(f"Video upstream API error | status={e.status_code} detail={e.detail}")
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="api_error",
            default_code="upstream_error",
        )
    except TaskNotFoundError as e:
        logger.error(f"Task not found | detail={e.detail}")
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="not_found",
            default_code="task_not_found",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled internal server error")
        return create_error_response(
            detail="Internal server error",
            status_code=500,
            error_type="server_error",
            default_code="internal_error",
        )


@router.get(
    "/generations/{task_id}",
    response_model=None,
    summary="查询视频任务状态（New API 通用格式）",
    description="查询任务状态，返回 {task_id, status, url, format, metadata, error}。",
)
async def get_video_generation_newapi(
    task_id: str,
    video_service: VideoService = Depends(get_video_service),
):
    """New API 通用格式的视频状态查询端点。

    返回 {task_id, status, url, format, metadata, error}；
    url 仅在任务完成后存在，取自上游 metadata.url。
    """
    try:
        logger.info(f"Video status query (new-api) | task_id={task_id}")
        video = await video_service.get_video_status(task_id)

        url = None
        if video.status == "completed":
            url = await video_service.get_video_url(task_id)

        metadata = video.metadata if isinstance(video.metadata, dict) else {}
        fmt = str(metadata.get("format") or "mp4").lower()
        error = video.error.model_dump(exclude_none=True) if video.error else None

        result: dict[str, Any] = {
            "task_id": task_id,
            "status": video.status,
        }
        if url:
            result["url"] = url
        result["format"] = fmt
        if metadata:
            result["metadata"] = metadata
        if error:
            result["error"] = error

        logger.info(f"Video status | task_id={task_id} status={video.status} has_url={'yes' if url else 'no'}")
        return result

    except UpstreamAPIError as e:
        logger.error(f"Video upstream API error | status={e.status_code} detail={e.detail}")
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="api_error",
            default_code="upstream_error",
        )
    except TaskNotFoundError as e:
        logger.error(f"Task not found | detail={e.detail}")
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="not_found",
            default_code="task_not_found",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled internal server error")
        return create_error_response(
            detail="Internal server error",
            status_code=500,
            error_type="server_error",
            default_code="internal_error",
        )


# ---------- 获取视频结果内容（流式） ----------
@router_v1_videos.get(
    "/v1/videos/{task_id}/content",
    summary="获取视频结果内容",
    description="流式回传视频内容（video/mp4，支持 Range）。",
)
async def get_video_content(
    request: Request,
    task_id: str,
    video_service: VideoService = Depends(get_video_service),
):
    """流式回传视频内容（非 307 重定向）。"""
    try:
        logger.info(f"Video content query | task_id={task_id}")
        video_url = await video_service.get_video_url(task_id)
        if not video_url:
            return create_error_response(
                detail="Video not ready or not found",
                status_code=404,
                error_type="not_found",
                default_code="video_not_ready",
            )
        return await stream_proxy(video_url, request, enforce_allowlist=True)

    except UpstreamAPIError as e:
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="api_error",
            default_code="upstream_error",
        )
    except TaskNotFoundError as e:
        return create_error_response(
            detail=e.detail,
            status_code=e.status_code,
            error_type="not_found",
            default_code="task_not_found",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled internal server error")
        return create_error_response(
            detail="Internal server error",
            status_code=500,
            error_type="server_error",
            default_code="internal_error",
        )
