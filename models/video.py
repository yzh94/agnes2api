"""视频模型相关的请求/响应数据模型。

对标 OpenAI Sora Video Generations API：
- 请求：model / prompt / size(4 枚举) / seconds("4"/"8"/"12") / input[](图生视频) / n / user
- 响应：Video 对象（id / object="video" / model / status / seconds / size / created_at / error）
- 内部适配：size/seconds/input -> 上游 Agnes 的 width/height/num_frames/image
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


# ========== Sora 请求枚举与映射 ==========

# OpenAI Sora size 枚举 -> (width, height)
# 注：具体分辨率需与上游 Agnes 视频能力核对，必要时调整映射
SORA_SIZE_MAP: dict[str, tuple[int, int]] = {
    "1920x1080": (1920, 1080),
    "1080x1920": (1080, 1920),
    "1024x1792": (1024, 1792),
    "1792x1024": (1792, 1024),
}

# OpenAI Sora seconds 枚举
SORA_SECONDS_VALUES = {"4", "8", "12"}


class VideoRequest(BaseModel):
    """创建视频任务的请求体（OpenAI Sora 兼容格式）。

    支持两类入参：
    - Sora 标准字段：size / seconds / input（图生视频）
    - 兼容旧字段：width / height / duration / fps（向后兼容，内部适配）
    """

    model: Optional[str] = Field(default=None, description="模型名称，默认 agnes-video-v2.0")
    prompt: Optional[str] = Field(default=None, description="视频内容的文本描述")

    # --- OpenAI Sora 字段 ---
    size: Optional[str] = Field(default=None, description="视频尺寸枚举，如 1920x1080")
    seconds: Optional[str] = Field(default=None, description='视频时长枚举："4"/"8"/"12"')
    input: Optional[list[Any]] = Field(default=None, description="图生视频输入项数组 [{type:image,url:...}]")
    n: int = Field(default=1, description="生成视频数量（上游仅支持 1）")
    user: Optional[str] = Field(default=None, description="用户标识符")

    # --- 兼容旧字段（向后兼容）---
    image: Optional[str] = Field(default=None, description="图生视频图片 URL（旧字段）")
    duration: Optional[float] = Field(default=None, description="视频时长（秒，旧字段）")
    width: Optional[int] = Field(default=None, description="视频宽度（旧字段）")
    height: Optional[int] = Field(default=None, description="视频高度（旧字段）")
    fps: Optional[int] = Field(default=None, description="视频帧率（旧字段）")
    num_inference_steps: Optional[int] = Field(default=None, description="推理步数")
    seed: Optional[int] = Field(default=None, description="随机种子")
    negative_prompt: Optional[str] = Field(default=None, description="反向提示词")
    mode: Optional[str] = Field(default=None, description="生成模式: ti2vid / keyframes")
    extra_body: Optional[dict] = Field(default=None, description="扩展参数")
    metadata: Optional[dict] = Field(default=None, description="new-api 兼容扩展参数")
    response_format: Optional[str] = Field(default=None, description="响应格式（兼容忽略）")

    model_config = {"extra": "allow"}


class VideoError(BaseModel):
    """视频任务错误信息。"""

    code: Optional[Any] = Field(default=None, description="错误码")
    message: Optional[str] = Field(default=None, description="错误消息")


class Video(BaseModel):
    """OpenAI Sora 形态的 Video 响应对象。"""

    id: str = Field(..., description="视频任务 ID")
    object: str = Field(default="video", description="对象类型")
    model: Optional[str] = Field(default=None, description="模型名称")
    status: str = Field(..., description="任务状态: queued/in_progress/completed/failed")
    seconds: Optional[str] = Field(default=None, description='视频时长："4"/"8"/"12"')
    size: Optional[str] = Field(default=None, description="视频尺寸枚举")
    created_at: Optional[int] = Field(default=None, description="创建时间戳（Unix 秒）")
    error: Optional[VideoError] = Field(default=None, description="错误信息（failed 时可用）")


# ========== 上游 Agnes 模型 ==========


class AgnesVideoRequest(BaseModel):
    """Agnes 上游视频创建请求体。"""

    model: str = Field(..., description="模型名称")
    prompt: Optional[str] = Field(default=None, description="视频内容描述")
    image: Optional[str] = Field(default=None, description="图生视频图片 URL")
    mode: Optional[str] = Field(default=None, description="生成模式")
    height: Optional[int] = Field(default=768, description="视频高度")
    width: Optional[int] = Field(default=1152, description="视频宽度")
    num_frames: Optional[int] = Field(default=None, description="视频帧数")
    frame_rate: Optional[float] = Field(default=24, description="视频帧率")
    num_inference_steps: Optional[int] = Field(default=None, description="推理步数")
    seed: Optional[int] = Field(default=None, description="随机种子")
    negative_prompt: Optional[str] = Field(default=None, description="反向提示词")
    extra_body: Optional[dict] = Field(default=None, description="扩展参数")


class AgnesVideoResponse(BaseModel):
    """Agnes 上游视频创建响应体（字段全部可选，避免上游少字段即 502）。"""

    id: Optional[str] = Field(default=None)
    task_id: Optional[str] = Field(default=None)
    video_id: Optional[str] = Field(default=None)
    object: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    status: Optional[str] = Field(default=None)
    progress: Optional[int] = Field(default=None)
    created_at: Optional[int] = Field(default=None)
    seconds: Optional[str] = Field(default=None)
    size: Optional[str] = Field(default=None)
    error: Optional[dict] = Field(default=None)
