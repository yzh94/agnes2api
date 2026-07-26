"""应用配置管理，从环境变量 / .env 文件加载配置。"""

import logging
from typing import Iterator

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ========== Agnes API 配置 ==========
    agnes_base_url: str = "https://apihub.agnes-ai.com"
    
    # ========== 服务配置 ==========
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    server_api_key: str = ""

    # ========== 请求配置 ==========
    # 默认 300s，图片生成可能需要较长时间
    request_timeout: float = 300.0

    # ========== 并发控制配置 ==========
    # 是否启用并行调用（n>1 时并行发送请求）
    # 关闭时保持原有串行行为
    enable_parallel_calls: bool = True

    # ========== 数据库配置 (SQLite) ==========
    database_url: str = "sqlite:///agnes2api.db"

    # ========== JWT 密钥 ==========
    jwt_secret: str = ""

    # ========== 图片代理配置 ==========
    # CDN URL 是否重写为 /proxy/image 以绕过 CORS（off: 对齐 OpenAI 规范，返回原始 CDN URL；on: 重写）
    image_url_proxy_mode: str = "on"

    # ========== 视频任务配置 ==========
    video_default_model: str = "agnes-video-v2.0"  # 默认视频模型
    video_default_duration: float = 5.0  # 默认视频时长(秒)
    video_default_width: int = 1152  # 默认宽度
    video_default_height: int = 768  # 默认高度
    video_default_fps: int = 24  # 默认帧率
    video_task_expire_seconds: int = 3600  # 任务记录过期时间(秒)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @field_validator("server_port")
    @classmethod
    def validate_server_port(cls, v: int) -> int:
        """验证端口号范围。"""
        if not (1 <= v <= 65535):
            raise ValueError(f"无效的端口号: {v}，必须在 1-65535 范围内")
        return v

    @field_validator("request_timeout")
    @classmethod
    def validate_request_timeout(cls, v: float) -> float:
        """验证超时时间必须为正数。"""
        if v <= 0:
            raise ValueError(f"无效的超时时间: {v}，必须为正数")
        return v

    @model_validator(mode="after")
    def validate_sensitive_fields(self) -> "Settings":
        """校验敏感字段不能为空。"""
        if not self.jwt_secret or len(self.jwt_secret) < 32:
            raise ValueError("jwt_secret 必须至少 32 个字符，请通过环境变量或 .env 文件配置")
        return self

logger.info("Loading application configuration...")
try:
    settings = Settings()
    logger.info("Configuration loaded successfully")
except Exception as e:
    logger.error(f"Failed to load configuration: {e}")
    logger.info("Please check your .env file or environment variables.")
    raise


