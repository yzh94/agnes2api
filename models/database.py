import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.sql import func
from config import settings

logger = logging.getLogger(__name__)

# 创建异步数据库引擎
engine = create_async_engine(
    settings.database_url,
    echo=False,  # 生产环境建议设为 False
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=30,
    pool_recycle=3600,  # 定期回收防止死连接
    pool_timeout=30,  # 连接超时（秒）
)

# 创建异步会话工厂
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False, default="")
    role = Column(String(20), default="user")  # 'admin' or 'user'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    # Discord OAuth 字段
    discord_id = Column(String(30), unique=True, index=True, nullable=True)
    discord_username = Column(String(100), nullable=True)


class ClientKey(Base):
    __tablename__ = "client_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False, unique=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    status = Column(String(20), default="active")  # 'active' or 'disabled'
    quota = Column(Float, default=-1.0)  # -1 means unlimited
    used_quota = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UpstreamKey(Base):
    __tablename__ = "upstream_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    weight = Column(Integer, default=1)
    status = Column(String(20), default="active")  # 'active' or 'disabled'
    disabled_reason = Column(Text, nullable=True)  # 自动禁用原因
    disabled_at = Column(DateTime(timezone=True), nullable=True)  # 自动禁用时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    client_key_id = Column(Integer, ForeignKey("client_keys.id", ondelete="SET NULL"), index=True, nullable=True)
    upstream_key = Column(String(100), nullable=False)
    model = Column(String(50), nullable=False)
    tokens = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SystemConfig(Base):
    __tablename__ = "system_configs"

    key = Column(String(50), primary_key=True)
    value = Column(String(255), nullable=False)

class AvailableModel(Base):
    __tablename__ = "available_models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)  # 对应 API 中请求的模型名称 (如 "agnes-2.0-flash")
    provider = Column(String(50), nullable=False)  # 归属体系: "openai", "gemini", "shared" 等
    type = Column(String(50), nullable=False)      # 类型: "text", "image", "video"
    is_active = Column(Boolean, default=True)      # 是否启用
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)  # 纯文本内容
    is_active = Column(Boolean, default=True)
    is_pinned = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


async def get_db():
    """获取数据库会话的依赖函数"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
            
async def init_db():
    """初始化数据库表并执行增量迁移。

    create_all 负责新建缺失的表；auto_migrate 负责检测已有表新增的列/索引，
    执行 ALTER TABLE 增量变更。幂等安全，重复启动无副作用。
    """
    try:
        async with engine.begin() as conn:
            def _create_all(sync_conn):
                Base.metadata.create_all(bind=sync_conn)
            await conn.run_sync(_create_all)
        logger.info("Database tables created (create_all) completed")
    except Exception as e:
        logger.error(f"create_all failed: {e}")
        raise

    try:
        from models.migrations import auto_migrate
        import inspect
        if inspect.iscoroutinefunction(auto_migrate):
            await auto_migrate()
        else:
            auto_migrate()
        logger.info("Schema migration completed successfully")
    except Exception as e:
        logger.error(f"Schema migration failed: {e}")
        raise
