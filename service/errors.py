"""公共错误处理工具模块。

提供 OpenAI 兼容的错误响应格式化功能，避免路由层代码重复。
"""

import logging
from typing import Any

from fastapi.responses import JSONResponse

from models.openai import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


class UpstreamAPIError(Exception):
    """上游 Agnes API 错误。"""

    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Upstream API error {status_code}")


def create_error_response(
    detail: Any,
    status_code: int = 500,
    error_type: str = "api_error",
    default_code: str = "upstream_error",
) -> JSONResponse:
    """创建 OpenAI 兼容的 JSON 错误响应。

    Args:
        detail: 错误详情
        status_code: HTTP 状态码
        error_type: 错误类型
        default_code: 默认错误代码

    Returns:
        JSONResponse 对象
    """
    try:
        if isinstance(detail, dict) and "error" in detail:
            err = detail["error"]
            msg = err.get("message", str(detail))
            code = err.get("code", default_code)
        elif isinstance(detail, dict):
            msg = detail.get("message", detail.get("error", str(detail)))
            code = detail.get("code", default_code)
        else:
            msg = str(detail)
            code = default_code
    except Exception:
        msg = str(detail)
        code = default_code

    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=ErrorDetail(message=msg, type=error_type, code=code)
        ).model_dump(exclude_none=True),
    )