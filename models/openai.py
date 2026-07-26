"""OpenAI Images API 兼容的请求 / 响应模型。

参考：https://platform.openai.com/docs/api-reference/images
"""

from typing import Optional

from pydantic import BaseModel, Field


class ImageRequest(BaseModel):
    """OpenAI Images API 标准请求体。

    除标准字段外，允许通过 extra="allow" 透传扩展参数（例如图生图的 image 数组）。

    gpt-image-1 专属字段（quality / style / output_format / background / moderation /
    partial_images / output_compression 等）通过 extra="allow" 接受，但**不转发**给上游
    Agnes 图片接口（上游不支持，转发会破坏生成）。
    """

    model: str = Field(..., description="模型名称，例如 agnes-image-2.1-flash")
    prompt: str = Field(..., description="图像生成的文本描述")
    size: str = Field(default="1024x1024", description="输出图像尺寸，默认 1024x1024")
    n: int = Field(default=1, description="生成图像数量，1-10", ge=1, le=10)
    response_format: Optional[str] = Field(
        default=None, description="返回格式：url 或 b64_json"
    )
    quality: Optional[str] = Field(default=None, description="图像质量（gpt-image-1 字段，接受不转发）")
    style: Optional[str] = Field(default=None, description="图像风格（gpt-image-1 字段，接受不转发）")
    user: Optional[str] = Field(default=None, description="终端用户标识（中转服务忽略）")

    # 图生图扩展：用户可在请求体中直接传入 image 数组
    image: Optional[list[str]] = Field(
        default=None, description="图生图输入图像 URL 或 Data URI Base64 数组"
    )

    # 文生图 Base64 输出
    return_base64: Optional[bool] = Field(
        default=None, description="文生图以 Base64 返回"
    )

    model_config = {"extra": "allow"}


class ImageUsage(BaseModel):
    """OpenAI Images 响应的 usage 对象（gpt-image-1）。"""

    input_tokens: Optional[int] = Field(default=None)
    output_tokens: Optional[int] = Field(default=None)
    total_tokens: Optional[int] = Field(default=None)


class ImageData(BaseModel):
    """单张图像的数据对象。"""

    url: Optional[str] = Field(default=None)
    b64_json: Optional[str] = Field(default=None, alias="b64_json")
    revised_prompt: Optional[str] = Field(default=None)


class ImageResponse(BaseModel):
    """OpenAI Images API 标准响应体。"""

    created: int = Field(..., description="创建时间戳（Unix 秒）")
    data: list[ImageData] = Field(default_factory=list)
    usage: Optional[ImageUsage] = Field(default=None, description="token 用量（上游有则透传）")


class ErrorDetail(BaseModel):
    message: str
    type: str
    param: Optional[str] = None
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail