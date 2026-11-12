"""应用配置管理，从环境变量 / .env 文件加载配置。"""

import logging

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ========== Agnes API 配置 ==========
    agnes_base_url: str = "https://apihub.agnes-ai.com"

    # ========== 服务自身地址（供内部跨接口调用使用） ==========
    app_base_url: str = "http://127.0.0.1:8000"
    
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

    # ========== 缓存配置 ==========
    # 是否启用请求缓存
    enable_cache: bool = False
    # 缓存最大条目数（LRU 淘汰）
    cache_max_size: int = 1000
    # 缓存过期时间（秒），默认 1 小时
    cache_ttl: int = 3600
    # 缓存键前缀，避免不同服务间冲突
    cache_key_prefix: str = "agnes2api"

    # ========== 数据库配置 ==========
    database_url: str = ""
    jwt_secret: str = ""

    # ========== 图片代理配置 ==========
    # CDN URL 是否重写为 /proxy/image 以绕过 CORS（off: 对齐 OpenAI 规范，返回原始 CDN URL；on: 重写）
    image_url_proxy_mode: str = "on"

    # ========== Redis 统计配置 ==========
    # Redis 连接字符串，格式: redis://[:password@]host:port/db
    # 示例: redis://default:PASSWORD@HOST:PORT/1
    # Key Pool 和 Stats 共用此连接，使用不同 key 前缀避免冲突
    redis_conn_string: str = ""

    # ========== 视频任务配置 ==========
    video_default_model: str = "agnes-video-v2.0"  # 默认视频模型
    video_default_duration: float = 5.0  # 默认视频时长(秒)
    video_default_width: int = 1152  # 默认宽度
    video_default_height: int = 768  # 默认高度
    video_default_fps: int = 24  # 默认帧率
    video_task_expire_seconds: int = 3600  # 任务记录过期时间(秒)

    # ========== 统计每日重置 ==========
    # 是否启用每日重置（清空 stats:* 重新统计）
    stats_daily_reset_enabled: bool = True
    # 每日重置时刻（北京时间 UTC+8 HH:MM）
    stats_daily_reset_time: str = "00:00"

    # ========== LLM 内容日志配置 ==========
    # 是否启用 LLM 请求输入/输出内容日志（JSONL 文件持久化）
    llm_content_log_enabled: bool = False

    # ========== Discord OAuth 配置 ==========
    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = ""

    # ========== 上游 Key 定时失败巡检 ==========
    # 是否启用定时失败巡检（只检 disabled Key：通过恢复、失败保持）
    upstream_key_validation_enabled: bool = True
    # 检验间隔（分钟），默认每小时一次
    upstream_key_validation_interval_minutes: int = 10

    # ========== Redis → MySQL 状态同步 ==========
    # Redis 为运行时真相源，周期性将 Redis 中 key 的 status/disabled_at/disabled_reason
    # 回写 MySQL，保证 MySQL 是新鲜的持久化镜像（兜底运行时异步写 DB 失败/延迟）。
    upstream_key_redis_sync_enabled: bool = True
    # 同步间隔（分钟）
    upstream_key_redis_sync_interval_minutes: int = 2

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
        """校验敏感字段不能为空，并强制要求使用 MySQL。"""
        if not self.database_url:
            raise ValueError("database_url 不能为空，请通过环境变量或 .env 文件配置")
        if not self.database_url.startswith("mysql+aiomysql://"):
            raise ValueError(
                "database_url 必须使用 MySQL 驱动，格式: mysql+aiomysql://user:pass@host:3306/dbname"
            )
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


