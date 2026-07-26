"""Agnes Image 2.1 Flash API 请求 / 响应模型。"""

from typing import Optional

from pydantic import BaseModel, Field


class AgnesExtraBody(BaseModel):
    """Agnes extra_body 嵌套结构，用于承载 response_format 和 image 等扩展参数。"""

    response_format: Optional[str] = Field(default=None)
    image: Optional[list[str]] = Field(default=None)

    model_config = {"extra": "allow"}


class AgnesImageRequest(BaseModel):
    """向 Agnes 上游发送的请求体。"""

    model: str = Field(default="agnes-image-2.1-flash")
    prompt: str
    size: str = "1024x1024"
    return_base64: Optional[bool] = Field(default=None)
    extra_body: Optional[AgnesExtraBody] = Field(default=None)

    model_config = {"extra": "allow"}