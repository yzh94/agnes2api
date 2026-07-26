"""视频服务层：处理视频任务的创建、状态查询和上游 API 调用。

对标 OpenAI Sora Video Generations API：
- 请求适配：size/seconds/input -> 上游 width/height/num_frames/image
- 响应：Video 对象（object="video"）
- Key 一致性：创建任务用的 Key 与查询用的 Key 必须一致；缓存丢失时返回 404，不遍历其他 Key
"""

import json
import logging
import re
import time
from typing import Any, Optional

from pydantic import ValidationError

from service.errors import UpstreamAPIError
from service.upstream_client import request_upstream_with_retry
from utils.http_client import get_http_client

from config import settings
from models.video import (
    AgnesVideoRequest,
    AgnesVideoResponse,
    SORA_SIZE_MAP,
    Video,
    VideoError,
    VideoRequest,
)
from service.simple_key_pool import get_key_pool_manager
from service.key_disable import check_and_disable_key_on_401

logger = logging.getLogger(__name__)


# 全局内存 task_info 存储（key: task_id -> {info dict}）
_task_cache: dict[str, dict] = {}
_task_cache_lock = __import__('threading').Lock()


def _save_task_info(task_id: str, info: dict) -> None:
    """保存视频任务信息到内存。"""
    with _task_cache_lock:
        _task_cache[task_id] = info
        # 清理过期的条目
        now = int(time.time())
        expired = [tid for tid, t in _task_cache.items() if t.get("expires_at", 0) < now]
        for tid in expired:
            del _task_cache[tid]


def _get_task_info(task_id: str) -> Optional[dict]:
    """从内存获取视频任务信息。"""
    with _task_cache_lock:
        return _task_cache.get(task_id)


# 上游状态 -> OpenAI Sora 状态归一化
_STATUS_MAP = {
    "queued": "queued",
    "pending": "queued",
    "in_progress": "in_progress",
    "processing": "in_progress",
    "running": "in_progress",
    "completed": "completed",
    "complete": "completed",
    "success": "completed",
    "succeeded": "completed",
    "done": "completed",
    "failed": "failed",
    "error": "failed",
    "cancelled": "failed",
    "canceled": "failed",
}


def _normalize_status(raw: Any) -> str:
    """将上游状态归一化为 OpenAI Sora 四态：queued/in_progress/completed/failed。"""
    return _STATUS_MAP.get(str(raw or "").lower(), "in_progress")


def adjust_num_frames(target_frames: int, max_frames: int = 441) -> int:
    """将目标帧数调整为符合 8n+1 规则的值，且不超过最大值。"""
    target_frames = min(target_frames, max_frames)
    target_frames = max(target_frames, 1)
    n_lower = (target_frames - 1) // 8
    n_upper = n_lower + 1
    frames_lower = 8 * n_lower + 1
    frames_upper = 8 * n_upper + 1
    if frames_upper > max_frames:
        return frames_lower
    if abs(frames_upper - target_frames) < abs(frames_lower - target_frames):
        return frames_upper
    return frames_lower


def _parse_size(size_str: str) -> tuple[int, int]:
    """解析分辨率字符串 "WxH" 为 (width, height)。"""
    match = re.match(r"(\d+)x(\d+)", size_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 0, 0


class VideoService:
    """视频服务类，处理视频任务的创建和状态查询。"""

    async def create_video_task(self, req: VideoRequest, user_id: int = 0) -> Video:
        """创建视频任务，返回 OpenAI Sora Video 对象。"""
        # 1. 参数验证
        if not req.prompt and not req.image and not req.input:
            raise UpstreamAPIError(
                status_code=400,
                detail={
                    "message": "Either 'prompt' or 'input' must be provided",
                    "type": "invalid_request_error",
                    "param": "prompt",
                    "code": "invalid_request",
                },
            )

        # n>1 上游不支持
        if req.n and req.n > 1:
            raise UpstreamAPIError(
                status_code=400,
                detail={
                    "message": "Video generation only supports n=1",
                    "type": "invalid_request_error",
                    "param": "n",
                    "code": "invalid_n",
                },
            )

        # 2. new-api 兼容：从 metadata 提取 negative_prompt
        if req.metadata and not req.negative_prompt:
            neg = req.metadata.get("negative_prompt")
            if neg:
                req.negative_prompt = neg

        # 3. 模型
        model = req.model or settings.video_default_model

        # 4. 适配 Sora size/seconds/input -> Agnes width/height/num_frames/image
        width = req.width
        height = req.height
        size_str = req.size
        if size_str:
            if size_str in SORA_SIZE_MAP:
                width, height = SORA_SIZE_MAP[size_str]
            else:
                w, h = _parse_size(size_str)
                if w and h:
                    width, height = w, h
        width = width or settings.video_default_width
        height = height or settings.video_default_height

        fps = req.fps or settings.video_default_fps
        if req.seconds is not None:
            try:
                duration = float(req.seconds)
            except (ValueError, TypeError):
                duration = settings.video_default_duration
        elif req.duration is not None:
            duration = req.duration
        else:
            duration = settings.video_default_duration
        raw_frames = int(duration * fps)
        num_frames = adjust_num_frames(raw_frames)

        # input[] -> image（图生视频，取首个图片 URL）
        image = req.image
        if not image and req.input:
            for item in req.input:
                if isinstance(item, str):
                    image = item
                    break
                if isinstance(item, dict) and item.get("url"):
                    image = item["url"]
                    break

        logger.info(
            f"Video task creation | size={size_str or f'{width}x{height}'} "
            f"seconds={req.seconds} duration={duration}s fps={fps} "
            f"raw_frames={raw_frames} -> num_frames={num_frames} "
            f"has_image={'yes' if image else 'no'}"
        )

        # 5. 构建 Agnes 上游请求
        agnes_extra_body: dict[str, Any] = req.extra_body.copy() if req.extra_body else {}
        top_mode = req.mode
        if req.mode == "keyframes" or (req.extra_body and "image" in req.extra_body):
            agnes_extra_body["mode"] = "keyframes"
            if req.extra_body and "image" in req.extra_body:
                agnes_extra_body["image"] = req.extra_body["image"]

        agnes_req = AgnesVideoRequest(
            model=model,
            prompt=req.prompt or "",
            image=image,
            mode=top_mode,
            height=height,
            width=width,
            num_frames=num_frames,
            frame_rate=float(fps),
            num_inference_steps=req.num_inference_steps,
            seed=req.seed,
            negative_prompt=req.negative_prompt,
            extra_body=agnes_extra_body if agnes_extra_body else None,
        )
        payload = agnes_req.model_dump(exclude_none=True, by_alias=True)
        logger.debug(f"Agnes upstream payload: {payload}")

        # 6. 调用上游（max_retries=0：视频创建昂贵，网络超时后不重试避免重复任务）
        try:
            http_resp, used_key = await request_upstream_with_retry(
                method="POST",
                url_template=f"{settings.agnes_base_url}/v1/videos",
                model_type="video",
                payload=payload,
                max_retries=0,
                user_id=user_id,
            )
            agnes_resp_data = http_resp.json()
            agnes_resp = AgnesVideoResponse(**agnes_resp_data)
        except UpstreamAPIError:
            raise
        except ValidationError as e:
            raise UpstreamAPIError(
                status_code=502,
                detail={
                    "message": f"Unexpected upstream video response schema: {str(e)}",
                    "type": "upstream_error",
                    "param": None,
                    "code": "invalid_upstream_response",
                },
            )
        except Exception as e:
            raise UpstreamAPIError(
                status_code=502,
                detail={
                    "message": f"Failed to call upstream API: {str(e)}",
                    "type": "upstream_error",
                    "param": None,
                    "code": "upstream_error",
                },
            )

        key_pool = get_key_pool_manager()
        masked_key = key_pool._compute_key_prefix(used_key)

        # 7. task_id = 上游 video_id（直接返给客户端，缓存丢失也可用真实 id 查询）
        video_id = agnes_resp.video_id or agnes_resp.id or agnes_resp.task_id
        if not video_id:
            raise UpstreamAPIError(
                status_code=502,
                detail={
                    "message": "Upstream did not return a video id",
                    "type": "upstream_error",
                    "code": "invalid_upstream_response",
                },
            )
        task_id = video_id

        # 8. 持久化 task_info 到内存 dict（含 used_key，供查询复用同一把 Key）
        task_info = {
            "video_id": video_id,
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + settings.video_task_expire_seconds,
            "model": model,
            "seconds": req.seconds,
            "size": size_str,
            "used_key": used_key,
            "used_key_masked": masked_key,
        }
        _save_task_info(task_id, task_info)

        logger.info(f"Video task created | task_id={task_id} using_key_prefix={masked_key}")

        # 9. 返回 Sora Video 对象
        return Video(
            id=task_id,
            object="video",
            model=model,
            status=_normalize_status(agnes_resp.status or "queued"),
            seconds=req.seconds,
            size=size_str,
            created_at=agnes_resp.created_at or int(task_info["created_at"]),
            error=None,
        )

    async def _load_task_info(self, task_id: str) -> Optional[dict]:
        """从内存获取 task_info。"""
        return _get_task_info(task_id)

    async def _query_upstream(self, task_id: str) -> tuple[dict, Optional[dict]]:
        """用创建任务时的同一把 Key 查询上游（保证 Key 一致性）。

        task_info 丢失或 used_key 缺失时抛 TaskNotFoundError(404)，绝不遍历其他 Key。
        Returns: (agnes_query_data, task_info)
        """
        task_info = await self._load_task_info(task_id)
        if not task_info or not task_info.get("used_key"):
            raise TaskNotFoundError(
                status_code=404,
                detail={
                    "message": f"Task '{task_id}' not found or expired",
                    "type": "not_found",
                    "param": "task_id",
                    "code": "task_not_found",
                },
            )

        full_key = task_info["used_key"]
        video_id = task_info.get("video_id") or task_id

        key_pool = get_key_pool_manager()
        client = get_http_client()
        query_url = f"{settings.agnes_base_url}/agnesapi?video_id={video_id}"

        try:
            resp = await client.get(query_url, headers={"Authorization": f"Bearer {full_key}"})
        except Exception as e:
            logger.error(f"Video query upstream error: {e}")
            raise UpstreamAPIError(
                status_code=502,
                detail={"message": f"Upstream query failed: {str(e)}", "type": "upstream_error"},
            )

        if resp.status_code == 404:
            raise TaskNotFoundError(
                status_code=404,
                detail={
                    "message": f"Task/Video '{video_id}' not found on upstream",
                    "type": "not_found",
                    "param": "task_id",
                    "code": "task_not_found",
                },
            )

        if resp.status_code >= 400:
            try:
                err_body = resp.json()
            except Exception:
                err_body = {"error": {"message": resp.text}}
            # 401：令牌失效，禁用该 Key（不可换 Key，因必须用同一把 Key 查询）
            if resp.status_code == 401:
                await check_and_disable_key_on_401(full_key, resp.status_code, err_body)
            raise UpstreamAPIError(status_code=resp.status_code, detail=err_body)

        # 成功（查询成功不记录 Key 池统计，仅创建时记录）
        try:
            agnes_query_data = resp.json()
        except Exception as e:
            raise UpstreamAPIError(
                status_code=502,
                detail={"message": f"Failed to parse upstream response: {e}"},
            )
        return agnes_query_data, task_info

    @staticmethod
    def _extract_video_url(agnes_query_data: dict) -> Optional[str]:
        """从上游查询响应提取视频结果 URL。

        注：上游真实字段未完全确认，保留多字段兜底；remixed_from_video_id 字段名像 ID，
        但历史观察其承载结果 URL，故保留为兜底，待上游文档确认后收敛。
        """
        video_url = (
            agnes_query_data.get("remixed_from_video_id")
            or agnes_query_data.get("video_url")
            or agnes_query_data.get("url")
        )
        if not video_url:
            outputs = agnes_query_data.get("outputs")
            if isinstance(outputs, list) and outputs:
                output = outputs[0]
                if isinstance(output, str):
                    video_url = output
                elif isinstance(output, dict):
                    video_url = output.get("url") or output.get("video_url")
        return video_url

    async def get_video_status(self, task_id: str) -> Video:
        """查询视频任务状态，返回 OpenAI Sora Video 对象（不含 url）。"""
        agnes_query_data, task_info = await self._query_upstream(task_id)

        status = _normalize_status(agnes_query_data.get("status"))
        logger.info(f"Video task query | task_id={task_id} status={status}")

        seconds = agnes_query_data.get("seconds") or (task_info.get("seconds") if task_info else None)
        size = agnes_query_data.get("size") or (task_info.get("size") if task_info else None)
        created_at = agnes_query_data.get("created_at") or (task_info.get("created_at") if task_info else None)
        model = task_info.get("model") if task_info else None

        error = None
        if status == "failed" or agnes_query_data.get("error"):
            err_data = agnes_query_data.get("error") or {}
            if isinstance(err_data, dict):
                error = VideoError(code=err_data.get("code"), message=err_data.get("message"))

        return Video(
            id=task_id,
            object="video",
            model=model,
            status=status,
            seconds=seconds,
            size=size,
            created_at=created_at,
            error=error,
        )

    async def get_video_url(self, task_id: str) -> Optional[str]:
        """查询视频结果 URL（供 /content 流式回传）。未完成则返回 None。"""
        agnes_query_data, _ = await self._query_upstream(task_id)
        status = _normalize_status(agnes_query_data.get("status"))
        if status != "completed":
            return None
        url = self._extract_video_url(agnes_query_data)
        logger.info(f"Parsed Video URL: {url} from keys: {list(agnes_query_data.keys())}")
        return url


# ---------- 异常定义 ----------


class VideoServiceError(Exception):
    """视频服务基础异常。"""

    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Video service error {status_code}")


class TaskNotFoundError(VideoServiceError):
    """任务不存在错误。"""

    pass


# ---------- 全局服务实例 ----------

_video_service: Optional[VideoService] = None


def get_video_service() -> VideoService:
    """获取视频服务单例。"""
    global _video_service
    if _video_service is None:
        _video_service = VideoService()
    return _video_service
